-- ============================================================
-- Migration 003 — Outreach safety layers + job queue + entitlements
-- Phase 2 of docs/architecture.md (triggered: platform build-out)
-- Suppression lists / Integration connections (OAuth) /
-- Job queue columns (leases) / Org entitlement limits
-- ============================================================

-- ------------------------------------------------------------
-- Suppression — who must NEVER be contacted (org-scoped)
-- ------------------------------------------------------------
create table if not exists public.suppression_entries (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  channel text not null default 'all',              -- email | whatsapp | sms | all
  value text not null,                              -- normalized email / phone
  reason text not null,                             -- unsubscribed | bounced | complained | manual | legal
  source text not null default 'manual',            -- manual | pipeline | provider_webhook
  created_at timestamptz not null default now(),
  unique (organization_id, channel, value)
);
create index if not exists idx_suppression_lookup
  on public.suppression_entries(organization_id, channel, value);

alter table public.suppression_entries enable row level security;
drop policy if exists suppression_manage_admin on public.suppression_entries;
create policy suppression_manage_admin on public.suppression_entries
  for all to authenticated
  using (
    exists (
      select 1 from public.organization_members me
      where me.organization_id = suppression_entries.organization_id
        and me.user_id = (select auth.uid())
        and me.role in ('owner', 'admin', 'member')
    )
  )
  with check (
    exists (
      select 1 from public.organization_members me
      where me.organization_id = suppression_entries.organization_id
        and me.user_id = (select auth.uid())
        and me.role in ('owner', 'admin', 'member')
    )
  );

-- ------------------------------------------------------------
-- Integration connections — per-tenant OAuth connections
-- One platform OAuth app serves all tenants; tokens encrypted at rest.
-- ------------------------------------------------------------
create table if not exists public.integration_connections (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  provider text not null,                           -- google | hubspot | microsoft | linkedin
  status text not null default 'pending',           -- pending | connected | error | revoked
  scopes text[] not null default '{}',
  provider_account_id text,
  provider_account_email text,
  access_token_enc text,                            -- AES-GCM hex (secrets.py)
  refresh_token_enc text,
  expires_at timestamptz,
  last_refresh_at timestamptz,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, provider)
);
create index if not exists idx_intconn_org on public.integration_connections(organization_id, provider);

alter table public.integration_connections enable row level security;
drop policy if exists intconn_manage_admin on public.integration_connections;
create policy intconn_manage_admin on public.integration_connections
  for all to authenticated
  using (
    exists (
      select 1 from public.organization_members me
      where me.organization_id = integration_connections.organization_id
        and me.user_id = (select auth.uid())
        and me.role in ('owner', 'admin')
    )
  )
  with check (
    exists (
      select 1 from public.organization_members me
      where me.organization_id = integration_connections.organization_id
        and me.user_id = (select auth.uid())
        and me.role in ('owner', 'admin')
    )
  );

-- ------------------------------------------------------------
-- Entitlement limits per org (plan enforcement source of truth)
-- ------------------------------------------------------------
alter table public.organizations
  add column if not exists limits jsonb not null default '{}'::jsonb;
-- shape: {"max_jobs_per_day": 10, "max_leads_per_month": 5000,
--         "max_provider_calls_per_day": 2000, "channels": ["email"]}

-- ------------------------------------------------------------
-- Job queue: leases + retries on the engine jobs table
-- ------------------------------------------------------------
alter table engine.jobs add column if not exists attempts int not null default 0;
alter table engine.jobs add column if not exists max_attempts int not null default 3;
alter table engine.jobs add column if not exists lease_expires_at timestamptz;
alter table engine.jobs add column if not exists worker_id text;

create index if not exists idx_engine_jobs_queue
  on engine.jobs(created_at) where state in ('QUEUED', 'RESUMING');
