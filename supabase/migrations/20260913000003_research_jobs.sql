-- 20260913000003_research_jobs.sql
-- R2 — persistent research jobs. The research state machine lives on the
-- SAME engine.jobs table (extended states live in code TRANSITIONS); this
-- table carries the resumable per-job context: objective, plan, budgets,
-- counters, stop_reason. Process memory is never the source of truth —
-- a worker restart must be able to continue any research job from here.

create table if not exists engine.research_context (
  job_id text primary key references engine.jobs(job_id) on delete cascade,
  organization_id uuid references public.organizations(id) on delete cascade,
  kind text not null default 'research',     -- research | legacy
  objective text not null,
  icp_version_id text,
  plan_json text,
  budget_json text,
  counters_json text,
  stop_reason text,
  stop_detail text,
  parent_job_id text,
  created_at text not null,
  updated_at text not null
);
create index if not exists idx_research_context_org
  on engine.research_context (organization_id, created_at desc);

do $$
begin
  execute 'grant select, insert, update, delete on all tables in schema engine to lead_engine';
  execute 'alter default privileges in schema engine'
          ' grant select, insert, update, delete on tables to lead_engine';
end $$;

alter table engine.research_context enable row level security;
alter table engine.research_context force row level security;
drop policy if exists tenant_isolation on engine.research_context;
create policy tenant_isolation on engine.research_context
  using (
    organization_id::text = coalesce(current_setting('app.current_org', true), '')
  )
  with check (
    organization_id::text = coalesce(current_setting('app.current_org', true), '')
  );
