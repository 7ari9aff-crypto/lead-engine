-- ============================================================
-- Migration 002 — Engine schema (operational data plane)
-- Phase 1 of docs/architecture.md
-- The engine's operational tables move from SQLite to the
-- dedicated `engine` schema. Service-role only: no RLS needed,
-- access revoked from anon/authenticated as defense in depth.
-- Business tables carry organization_id (tenant scope).
-- ============================================================

create schema if not exists engine;

revoke all on schema engine from anon, authenticated;

-- ------------------------------------------------------------
-- Provider registry (global config: priorities, quotas, status)
-- Per-org credentials live in public.organization_provider_credentials
-- ------------------------------------------------------------
create table if not exists engine.providers (
  name text not null,
  task text not null,
  type text,
  priority int default 99,
  quota_kind text,
  quota_limit numeric,
  quota_used numeric default 0,
  period text,
  period_start timestamptz,
  rpm_limit int,
  status text default 'active',
  status_reason text,
  cooldown_until timestamptz,
  env_key text,
  base_url text,
  model_name text,
  notes text,
  primary key (name, task)
);

-- ------------------------------------------------------------
-- Usage ledger — every provider call, org-scoped
-- ------------------------------------------------------------
create table if not exists engine.usage_ledger (
  id bigint generated always as identity primary key,
  ts timestamptz not null default now(),
  provider text not null,
  task text not null,
  job_id text,
  organization_id uuid references public.organizations(id) on delete set null,
  units numeric default 1,
  unit_kind text,
  status text,
  latency_ms int,
  prompt_tokens int default 0,
  completion_tokens int default 0,
  key_index int
);
create index if not exists idx_usage_provider_ts on engine.usage_ledger(provider, ts desc);
create index if not exists idx_usage_job on engine.usage_ledger(job_id);
create index if not exists idx_usage_org_ts on engine.usage_ledger(organization_id, ts desc);

-- ------------------------------------------------------------
-- Jobs (operational state machine) — org-scoped
-- ------------------------------------------------------------
create table if not exists engine.jobs (
  job_id text primary key,
  organization_id uuid not null references public.organizations(id) on delete cascade,
  icp_id text,
  state text not null,
  pause_reason text,
  resume_at timestamptz,
  params jsonb,
  result jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists idx_engine_jobs_org on engine.jobs(organization_id, created_at desc);
create index if not exists idx_engine_jobs_state on engine.jobs(state);

create table if not exists engine.job_events (
  id bigint generated always as identity primary key,
  ts timestamptz not null default now(),
  job_id text not null,
  from_state text,
  to_state text,
  reason text
);
create index if not exists idx_engine_job_events_job on engine.job_events(job_id, id);

-- ------------------------------------------------------------
-- Leads — org-scoped, mirrors the SQLite LEAD_COLUMNS contract
-- ------------------------------------------------------------
create table if not exists engine.leads (
  lead_id text primary key,
  organization_id uuid not null references public.organizations(id) on delete cascade,
  job_id text,
  name text,
  domain text,
  city text,
  country text,
  industry text,
  employee_count int,
  branches int,
  phone text,
  email text,
  email_status text,
  email_confidence numeric,
  decision_maker text,
  decision_maker_title text,
  linkedin text,
  website text,
  social text,
  qualification_score numeric,
  tier text,
  score numeric,
  stage text,                -- ACCEPTED | REVIEW | REJECTED
  processing_mode text,      -- cloud | degraded_local
  requires_review int default 0,
  legal_decision text,
  data_types text,
  sources text,
  source_queries text,
  raw jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists idx_engine_leads_org_stage
  on engine.leads(organization_id, stage, score desc);
create index if not exists idx_engine_leads_job on engine.leads(job_id);
create index if not exists idx_engine_leads_created
  on engine.leads(organization_id, created_at desc);

create table if not exists engine.evidence (
  id bigint generated always as identity primary key,
  lead_id text not null,
  claim text not null,
  source text,
  collection_method text,
  collected_at timestamptz not null default now(),
  expires_at timestamptz
);
create index if not exists idx_evidence_lead on engine.evidence(lead_id);

-- ------------------------------------------------------------
-- Three-level cache
-- ------------------------------------------------------------
create table if not exists engine.cache (
  level int not null,
  cache_key text not null,
  payload jsonb,
  data_type text,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null,
  primary key (level, cache_key)
);
create index if not exists idx_cache_expires on engine.cache(expires_at);

-- ------------------------------------------------------------
-- Agents control plane — runs are org-scoped
-- ------------------------------------------------------------
create table if not exists engine.agents (
  agent_id text primary key,
  slug text not null unique,
  name text not null,
  description text,
  status text not null default 'draft',
  current_version text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists engine.agent_versions (
  agent_id text not null,
  version text not null,
  instructions text,
  model_policy jsonb,
  tool_policy jsonb,
  output_schema jsonb,
  status text not null default 'draft',
  created_at timestamptz not null default now(),
  primary key (agent_id, version)
);

create table if not exists engine.agent_runs (
  run_id text primary key,
  agent_id text not null,
  organization_id uuid not null references public.organizations(id) on delete cascade,
  version text not null,
  status text not null,
  input_json jsonb,
  output_json jsonb,
  error text,
  cost_usd numeric default 0,
  prompt_tokens int default 0,
  completion_tokens int default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists idx_agent_runs_org on engine.agent_runs(organization_id, created_at desc);

create table if not exists engine.agent_steps (
  id bigint generated always as identity primary key,
  run_id text not null,
  step_name text not null,
  step_type text,
  status text not null,
  input_json jsonb,
  output_json jsonb,
  provider text,
  latency_ms int,
  error text,
  started_at timestamptz,
  finished_at timestamptz
);
create index if not exists idx_agent_steps_run on engine.agent_steps(run_id, id);

create table if not exists engine.tools (
  name text primary key,
  description text,
  input_schema jsonb,
  output_schema jsonb,
  scopes text,
  requires_approval int default 0,
  enabled int default 1,
  created_at timestamptz not null default now()
);

create table if not exists engine.connections (
  connection_id text primary key,
  provider text not null,
  kind text not null,
  base_url text,
  status text not null default 'unknown',
  last_checked_at timestamptz,
  metadata_json jsonb,
  created_at timestamptz not null default now()
);

create table if not exists engine.approvals (
  approval_id text primary key,
  run_id text not null,
  organization_id uuid not null references public.organizations(id) on delete cascade,
  step_id bigint,
  action text not null,
  payload_json jsonb,
  status text not null default 'PENDING',
  requested_at timestamptz not null default now(),
  resolved_at timestamptz
);
create index if not exists idx_approvals_org_status
  on engine.approvals(organization_id, status, requested_at desc);

-- ------------------------------------------------------------
-- Activity feed (platform-wide event timeline)
-- ------------------------------------------------------------
create table if not exists engine.activity_events (
  id bigint generated always as identity primary key,
  ts timestamptz not null default now(),
  kind text not null,
  payload_json jsonb,
  correlation_id text
);
create index if not exists idx_activity_kind_id on engine.activity_events(kind, id desc);
