-- 20260911000006_tenant_scoping.sql
-- P0.4 Data isolation audit: classify every engine table and close the
-- cross-tenant gaps the audit found.
--
-- CLASSIFICATION (authoritative):
--   Tenant-scoped (organization_id REQUIRED going forward):
--     jobs, leads, usage_ledger, agent_runs, approvals, job_events,
--     evidence, cache, notifications, agent_steps, activity_events, agents
--   Platform-global (shared, read-only to tenants):
--     providers (definitions), tools (registry)
--   Internal/deprecated (not tenant data, kept for legacy workers):
--     connections (agent-style provider connections; superseded by
--     public.integration_connections for OAuth)
--
-- agents: NULL organization_id = platform/system agent (e.g. the seeded
-- "lead-generation" agent). Tenant agents always carry their org.

-- 1) activity_events: tenant-scoped from now on (legacy rows stay NULL).
alter table engine.activity_events
  add column if not exists organization_id uuid
  references public.organizations(id) on delete cascade;
create index if not exists idx_activity_org_id
  on engine.activity_events(organization_id, id desc);

-- 2) agents: org-owned with platform agents allowed (NULL).
alter table engine.agents
  add column if not exists organization_id uuid
  references public.organizations(id) on delete cascade;
create index if not exists idx_agents_org on engine.agents(organization_id);

-- slug uniqueness becomes per-tenant: (organization_id, slug).
-- Postgres treats NULLs as distinct in unique indexes, so platform agents
-- (NULL org) can share nothing while tenants own their own namespace.
do $$
begin
  if exists (
    select 1 from pg_constraint
    where conname = 'agents_slug_key' and conrelid = 'engine.agents'::regclass
  ) then
    alter table engine.agents drop constraint agents_slug_key;
  end if;
end $$;
create unique index if not exists uq_agents_org_slug
  on engine.agents(coalesce(organization_id, '00000000-0000-0000-0000-000000000000'::uuid), slug);
