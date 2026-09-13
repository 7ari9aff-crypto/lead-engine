-- 20260913000001_truth_layer.sql
-- R1 — Truth Layer (docs/plan-agentic-research.md).
-- research_facts: the canonical fact store. The model is never the source of
-- truth: every fact carries value + status + provenance (fact_sources) +
-- freshness (collected_at/expires_at). Statuses are exactly:
--   VERIFIED | CONFLICTED | STALE | UNVERIFIED | INFERRED
-- Nothing in between — no "probably true".
--
-- fact_conflicts: unresolved value disagreements stay OPEN and VISIBLE;
-- resolution (auto or human) is recorded with who/when/why.
-- open_questions: agent-asked gaps that block progress (WAITING_FOR_USER).
-- visited_sources: research browsing trail per job (resume context).
-- icp_versions: versioned ICP definitions in the DB (YAML = import only).
--
-- All tables are tenant-scoped (organization_id) with FORCED RLS using the
-- same app.current_org policy as migration 007.

create table if not exists engine.research_facts (
  fact_id text primary key,
  organization_id uuid references public.organizations(id) on delete cascade,
  subject_kind text not null,           -- company | person | topic
  subject_id text not null,             -- lead_id / domain / person ref
  field text not null,                  -- phone | email | employee_count | ...
  value text not null,
  value_kind text not null default 'text',   -- text | number | bool | json
  status text not null default 'UNVERIFIED'
    check (status in ('VERIFIED','CONFLICTED','STALE','UNVERIFIED','INFERRED')),
  confidence real not null default 0.4,
  job_id text,
  run_id text,
  collected_at text not null,
  expires_at text,
  created_at text not null,
  updated_at text not null
);
create unique index if not exists uq_facts_subject_field_value
  on engine.research_facts
  (coalesce(organization_id, '00000000-0000-0000-0000-000000000000'::uuid),
   subject_kind, subject_id, field, value);
create index if not exists idx_facts_subject on engine.research_facts
  (organization_id, subject_kind, subject_id);

create table if not exists engine.fact_sources (
  id bigint generated always as identity primary key,
  organization_id uuid references public.organizations(id) on delete cascade,
  fact_id text not null references engine.research_facts(fact_id) on delete cascade,
  source_url text,
  source_kind text not null default 'search_api',
    -- search_api | openmanus | apollo | hunter | abstract | email_verify | manual | llm_inference
  provider text,
  query text,
  quote text,
  collected_at text not null
);
create index if not exists idx_fact_sources_fact on engine.fact_sources (fact_id);

create table if not exists engine.fact_conflicts (
  conflict_id text primary key,
  organization_id uuid references public.organizations(id) on delete cascade,
  subject_kind text not null,
  subject_id text not null,
  field text not null,
  fact_a text not null,
  fact_b text not null,
  winner text,
  resolution text not null default 'OPEN'
    check (resolution in ('OPEN','RESOLVED_AUTO','RESOLVED_HUMAN')),
  resolution_note text,
  resolved_by text,
  resolved_at text,
  job_id text,
  created_at text not null,
  updated_at text not null
);
create index if not exists idx_conflicts_open
  on engine.fact_conflicts (organization_id, subject_id, field)
  where resolution = 'OPEN';

create table if not exists engine.open_questions (
  id bigint generated always as identity primary key,
  organization_id uuid references public.organizations(id) on delete cascade,
  job_id text not null,
  subject_kind text not null default 'company',
  subject_id text,
  question text not null,
  status text not null default 'OPEN' check (status in ('OPEN','ANSWERED','DROPPED')),
  answer_fact_id text,
  created_at text not null,
  answered_at text
);
create index if not exists idx_open_questions_job
  on engine.open_questions (organization_id, job_id, status);

create table if not exists engine.visited_sources (
  id bigint generated always as identity primary key,
  organization_id uuid references public.organizations(id) on delete cascade,
  job_id text not null,
  url text not null,
  title text,
  http_status integer,
  summary text,
  fetched_at text not null,
  unique (job_id, url)
);

create table if not exists engine.icp_versions (
  icp_version_id text primary key,
  organization_id uuid references public.organizations(id) on delete cascade,
  slug text not null,
  version text not null,
  definition text not null,             -- JSON: full ICP dict
  source text not null default 'manual',   -- chat_intent | manual | yaml_import
  status text not null default 'draft' check (status in ('draft','active','retired')),
  created_by text,
  created_at text not null,
  updated_at text not null,
  unique (organization_id, slug, version)
);

-- RLS: mirror migration 007 for every new tenant-scoped table.
do $$
declare t text;
begin
  execute 'grant select, insert, update, delete on all tables in schema engine to lead_engine';
  execute 'grant usage, select on all sequences in schema engine to lead_engine';
  execute 'alter default privileges in schema engine'
          ' grant select, insert, update, delete on tables to lead_engine';
  execute 'alter default privileges in schema engine'
          ' grant usage, select on sequences to lead_engine';

  foreach t in array array['research_facts','fact_sources','fact_conflicts',
                           'open_questions','visited_sources','icp_versions']
  loop
    execute format('alter table engine.%I enable row level security', t);
    execute format('alter table engine.%I force row level security', t);
    execute format('drop policy if exists tenant_isolation on engine.%I', t);
    execute format($p$
      create policy tenant_isolation on engine.%I
      using (
        organization_id::text = coalesce(current_setting('app.current_org', true), '')
        or organization_id is null
      )
      with check (
        organization_id::text = coalesce(current_setting('app.current_org', true), '')
        or organization_id is null
      )
    $p$, t);
  end loop;
end $$;

-- leads.disposition — the human decision layer (Stage 3 lives in R5, the
-- column lands with the schema batch to keep one migration per layer).
alter table engine.leads add column if not exists disposition text
  check (disposition in ('APPROVE_CONTACT','REJECT','RESEARCH_MORE','SAVE_FOR_LATER'));
alter table engine.leads add column if not exists disposition_note text;
alter table engine.leads add column if not exists disposition_at text;
alter table engine.leads add column if not exists decided_by text;
