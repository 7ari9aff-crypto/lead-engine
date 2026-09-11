-- ============================================================
-- Migration 005 — Tenant provisioning state machine (Phase 3 code)
-- REQUESTED -> PROVISIONING -> ACTIVE (with FAILED + rollback),
-- steps recorded so no half-created tenant is ever visible.
-- ============================================================

create table if not exists engine.tenant_provisioning (
  org_id uuid primary key references public.organizations(id) on delete cascade,
  state text not null default 'REQUESTED',
  -- REQUESTED | PROVISIONING | ACTIVE | FAILED
  isolation_level text not null default 'pooled',
  steps jsonb not null default '[]'::jsonb,
  error text,
  requested_by text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
