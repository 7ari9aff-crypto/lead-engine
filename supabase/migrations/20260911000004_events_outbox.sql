-- ============================================================
-- Migration 004 — Event backbone: outbox + consumers + webhooks
-- + notifications (Phase 2 completion of docs/architecture.md)
-- Transactional outbox (at-least-once) + idempotent consumers
-- (event_id dedup) + DLQ semantics (status='dead').
-- ============================================================

-- ------------------------------------------------------------
-- Transactional outbox
-- ------------------------------------------------------------
create table if not exists engine.outbox (
  id bigint generated always as identity primary key,
  event_id text not null unique,                    -- idempotency key
  organization_id uuid,
  aggregate_type text not null,                     -- job | lead | usage | platform
  aggregate_id text,
  event_type text not null,                         -- job.completed, lead.verified, ...
  event_version int not null default 1,
  payload jsonb,
  status text not null default 'pending',           -- pending | dispatched | dead
  attempts int not null default 0,
  last_error text,
  created_at timestamptz not null default now(),
  published_at timestamptz
);
create index if not exists idx_outbox_dispatch
  on engine.outbox(status, created_at) where status = 'pending';
create index if not exists idx_outbox_org_type
  on engine.outbox(organization_id, event_type, created_at desc);

-- ------------------------------------------------------------
-- Consumer dedup — exactly-once side effects per (event, consumer)
-- ------------------------------------------------------------
create table if not exists engine.event_consumptions (
  event_id text not null,
  consumer text not null,
  processed_at timestamptz not null default now(),
  primary key (event_id, consumer)
);

-- ------------------------------------------------------------
-- Webhooks — org-registered endpoints receiving signed events
-- ------------------------------------------------------------
create table if not exists public.webhooks (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  url text not null,
  secret_enc text not null,                          -- AES-GCM hex (signing secret)
  events text[] not null default '{*}',              -- subscribed event types ('*' = all)
  status text not null default 'active',             -- active | paused
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists idx_webhooks_org on public.webhooks(organization_id);

alter table public.webhooks enable row level security;
drop policy if exists webhooks_manage_admin on public.webhooks;
create policy webhooks_manage_admin on public.webhooks
  for all to authenticated
  using (
    exists (
      select 1 from public.organization_members me
      where me.organization_id = webhooks.organization_id
        and me.user_id = (select auth.uid())
        and me.role in ('owner', 'admin')
    )
  )
  with check (
    exists (
      select 1 from public.organization_members me
      where me.organization_id = webhooks.organization_id
        and me.user_id = (select auth.uid())
        and me.role in ('owner', 'admin')
    )
  );

-- Delivery log (DLQ semantics: deliveries exhausted -> last row success=false)
create table if not exists engine.webhook_deliveries (
  id bigint generated always as identity primary key,
  webhook_id uuid,
  event_id text,
  url text,
  attempt int not null default 1,
  status_code int,
  success boolean not null default false,
  error text,
  created_at timestamptz not null default now()
);
create index if not exists idx_webhook_deliveries_event
  on engine.webhook_deliveries(event_id, created_at desc);

-- ------------------------------------------------------------
-- Notifications (in-app; email channel gated by SMTP env)
-- ------------------------------------------------------------
create table if not exists engine.notifications (
  id bigint generated always as identity primary key,
  organization_id uuid,
  kind text not null,                                -- job.completed | usage.threshold | ...
  title text not null,
  body jsonb,
  read int not null default 0,
  created_at timestamptz not null default now()
);
create index if not exists idx_notifications_org
  on engine.notifications(organization_id, read, created_at desc);
