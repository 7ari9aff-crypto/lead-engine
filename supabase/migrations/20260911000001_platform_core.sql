-- ============================================================
-- Migration 001 — Platform Core (tenancy foundation)
-- Phase 1 of docs/architecture.md — frozen baseline 2026-09-11
-- Organizations / Members (RBAC) / API keys (hashed) /
-- per-org provider credentials (encrypted) / audit log
-- ============================================================

-- ------------------------------------------------------------
-- Organizations (tenants)
-- ------------------------------------------------------------
create table if not exists public.organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  slug text not null unique,
  plan text not null default 'free',
  status text not null default 'active',
  isolation_level text not null default 'pooled',   -- pooled | isolated_compute | dedicated
  region text,
  settings jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ------------------------------------------------------------
-- Memberships (users <-> organizations) with RBAC roles
-- ------------------------------------------------------------
create table if not exists public.organization_members (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null default 'member',              -- owner | admin | member | viewer
  created_at timestamptz not null default now(),
  unique (organization_id, user_id)
);
create index if not exists idx_org_members_user
  on public.organization_members(user_id);
create index if not exists idx_org_members_org
  on public.organization_members(organization_id);

-- ------------------------------------------------------------
-- API keys (hashed at rest, org-scoped) for API / MCP consumers
-- ------------------------------------------------------------
create table if not exists public.api_keys (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  name text not null,
  key_hash text not null unique,                    -- sha256 hex of the full key
  key_prefix text not null,                         -- first 8 chars, display only
  scopes text[] not null default '{}',
  status text not null default 'active',
  last_used_at timestamptz,
  created_at timestamptz not null default now(),
  revoked_at timestamptz
);
create index if not exists idx_api_keys_org on public.api_keys(organization_id);

-- ------------------------------------------------------------
-- Per-org provider credentials (never stored plain)
-- Value is AES-GCM encrypted via pgcrypto; key lives in Vault.
-- ------------------------------------------------------------
create table if not exists public.organization_provider_credentials (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  provider_name text not null,
  env_key text not null,
  encrypted_value text not null,                    -- bytea-hex: iv || ciphertext
  key_version int not null default 1,
  status text not null default 'active',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, env_key)
);

-- ------------------------------------------------------------
-- Audit log (security-critical events)
-- ------------------------------------------------------------
create table if not exists public.audit_logs (
  id bigint generated always as identity primary key,
  organization_id uuid references public.organizations(id) on delete cascade,
  actor_user_id uuid,
  action text not null,
  target_type text,
  target_id text,
  detail jsonb,
  occurred_at timestamptz not null default now()
);
create index if not exists idx_audit_org_time
  on public.audit_logs(organization_id, occurred_at desc);

-- ------------------------------------------------------------
-- updated_at trigger for organizations
-- ------------------------------------------------------------
create or replace function public.touch_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists trg_organizations_touch on public.organizations;
create trigger trg_organizations_touch
  before update on public.organizations
  for each row execute function public.touch_updated_at();

-- ------------------------------------------------------------
-- Self-service tenancy: every new auth user gets a personal org
-- and becomes its owner. Runs as the platform (security definer,
-- table owner) because it fires on auth schema events.
-- ------------------------------------------------------------
create or replace function public.handle_new_user_org()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  new_org_id uuid;
  display_name text;
begin
  display_name := coalesce(
    new.raw_user_meta_data ->> 'full_name',
    split_part(new.email, '@', 1),
    'user-' || left(new.id::text, 8)
  );
  insert into public.organizations (name, slug)
  values (
    display_name || '''s workspace',
    'org-' || left(new.id::text, 8) || '-' ||
      substr(md5(random()::text || clock_timestamp()::text), 1, 6)
  )
  returning id into new_org_id;

  insert into public.organization_members (organization_id, user_id, role)
  values (new_org_id, new.id, 'owner');
  return new;
end;
$$;

drop trigger if exists trg_auth_user_org on auth.users;
create trigger trg_auth_user_org
  after insert on auth.users
  for each row execute function public.handle_new_user_org();

-- advisors: the definer trigger function must not be callable via RPC
revoke execute on function public.handle_new_user_org() from anon, authenticated, public;

-- ------------------------------------------------------------
-- RLS — enabled on every table above
-- ------------------------------------------------------------
alter table public.organizations enable row level security;
alter table public.organization_members enable row level security;
alter table public.api_keys enable row level security;
alter table public.organization_provider_credentials enable row level security;
alter table public.audit_logs enable row level security;

-- organizations: members read, admins manage
drop policy if exists org_select_member on public.organizations;
create policy org_select_member on public.organizations
  for select to authenticated
  using (
    exists (
      select 1 from public.organization_members m
      where m.organization_id = organizations.id
        and m.user_id = (select auth.uid())
    )
  );

drop policy if exists org_update_admin on public.organizations;
create policy org_update_admin on public.organizations
  for update to authenticated
  using (
    exists (
      select 1 from public.organization_members m
      where m.organization_id = organizations.id
        and m.user_id = (select auth.uid())
        and m.role in ('owner', 'admin')
    )
  )
  with check (
    exists (
      select 1 from public.organization_members m
      where m.organization_id = organizations.id
        and m.user_id = (select auth.uid())
        and m.role in ('owner', 'admin')
    )
  );

-- members: see co-members of own orgs, admins manage
drop policy if exists member_select_same_org on public.organization_members;
create policy member_select_same_org on public.organization_members
  for select to authenticated
  using (
    exists (
      select 1 from public.organization_members me
      where me.organization_id = organization_members.organization_id
        and me.user_id = (select auth.uid())
    )
  );

drop policy if exists member_manage_admin on public.organization_members;
create policy member_manage_admin on public.organization_members
  for all to authenticated
  using (
    exists (
      select 1 from public.organization_members me
      where me.organization_id = organization_members.organization_id
        and me.user_id = (select auth.uid())
        and me.role in ('owner', 'admin')
    )
  )
  with check (
    exists (
      select 1 from public.organization_members me
      where me.organization_id = organization_members.organization_id
        and me.user_id = (select auth.uid())
        and me.role in ('owner', 'admin')
    )
  );

-- api keys: org admins only
drop policy if exists apikey_manage_admin on public.api_keys;
create policy apikey_manage_admin on public.api_keys
  for all to authenticated
  using (
    exists (
      select 1 from public.organization_members me
      where me.organization_id = api_keys.organization_id
        and me.user_id = (select auth.uid())
        and me.role in ('owner', 'admin')
    )
  )
  with check (
    exists (
      select 1 from public.organization_members me
      where me.organization_id = api_keys.organization_id
        and me.user_id = (select auth.uid())
        and me.role in ('owner', 'admin')
    )
  );

-- provider credentials: org admins only
drop policy if exists cred_manage_admin on public.organization_provider_credentials;
create policy cred_manage_admin on public.organization_provider_credentials
  for all to authenticated
  using (
    exists (
      select 1 from public.organization_members me
      where me.organization_id = organization_provider_credentials.organization_id
        and me.user_id = (select auth.uid())
        and me.role in ('owner', 'admin')
    )
  )
  with check (
    exists (
      select 1 from public.organization_members me
      where me.organization_id = organization_provider_credentials.organization_id
        and me.user_id = (select auth.uid())
        and me.role in ('owner', 'admin')
    )
  );

-- audit: readable by org admins, written by backend (service role)
drop policy if exists audit_read_admin on public.audit_logs;
create policy audit_read_admin on public.audit_logs
  for select to authenticated
  using (
    exists (
      select 1 from public.organization_members me
      where me.organization_id = audit_logs.organization_id
        and me.user_id = (select auth.uid())
        and me.role in ('owner', 'admin')
    )
  );
