-- ============================================================
-- Migration — engine.audit_logs
--
-- Why: `audit_logs` is the ONE table, out of the 27 the
-- application's SQL references, that does not resolve at runtime.
-- The engine connects with `options="-c search_path=engine"`
-- (lead_engine/db_pg.py __init__), and `audit_logs` was only ever
-- created in `public` (Supabase default) and in the SQLite schema
-- (lead_engine/db.py SCHEMA). So on Postgres every write raises:
--
--   psycopg.errors.UndefinedTable: relation "audit_logs" does not exist
--
-- Verified by executing, under the exact runtime search_path:
--   show search_path -> engine
--   SELECT count(*) FROM audit_logs -> UndefinedTable
--   to_regclass('engine.audit_logs') -> NULL
--
-- Impact is a silent compliance failure, not a crash at boot:
-- PgDatabase.audit() (db_pg.py:165) and Database.audit() (db.py:455)
-- and codeops.py:142 INSERT into it. Two of the three call sites in
-- api/review_api.py (:126, :201) are NOT wrapped in try/except and
-- run AFTER the mutation's own db.execute() has already committed
-- (autocommit=False + immediate per-statement commit). So on
-- production an operator approving, rejecting or re-qualifying a
-- lead has their change persisted, receives HTTP 500, and leaves no
-- audit record. SQLite has the table, so the whole suite passes and
-- CI stays green — this only fails in production.
--
-- Second half of the finding, NOT fixed by this migration: nothing in
-- the codebase ever SELECTs from audit_logs. The table is write-only.
-- The dashboard's "سجل النشاط والتدقيق (Audit Trail)" page builds its
-- operator rows from localStorage (web/src/lib/audit.ts:19), which is
-- per-browser, lost on another device, and unavailable to a second
-- operator or to any access request. A real audit surface needs a read
-- path over this table; tracked separately.
--
-- Types follow the existing engine convention (payload_json jsonb,
-- created_at timestamptz, id bigint identity, matching
-- leads/jobs/approvals/activity_events) EXCEPT organization_id, which is
-- deliberately `text` rather than `uuid`.
--
-- Why text: db.audit() passes `getattr(self, "org_id", None)` straight
-- through, and the codebase has a '__no_org__' machine-context sentinel that
-- _inject_org explicitly refuses to inject precisely because it is not a
-- valid uuid. A uuid column would reject that write with a cast error, which
-- reproduces the exact failure this migration exists to end: a 500 raised
-- from the audit call after the operator's mutation has already committed.
-- An audit/provenance row must never be lost to a tenant-type mismatch, and
-- this column is descriptive provenance, not a foreign key.
create table if not exists engine.audit_logs (
  id bigint generated always as identity primary key,
  organization_id text,
  actor text not null,
  action text not null,
  entity_type text,
  entity_id text,
  payload_json jsonb,
  created_at timestamptz not null default now()
);

-- The only read the surface will need first: newest actions for one
-- tenant, and provenance for a single entity.
create index if not exists audit_logs_org_created_idx
  on engine.audit_logs (organization_id, created_at desc);

create index if not exists audit_logs_entity_idx
  on engine.audit_logs (entity_type, entity_id);

-- Tenant scoping: engine.audit_logs must be reachable unqualified by the
-- app role, whose search_path is pinned to `engine`.
grant usage on schema engine to lead_engine;
grant select, insert, references, trigger on engine.audit_logs to lead_engine;
-- Sequence for the identity column: INSERT fails without this.
grant usage on all sequences in schema engine to lead_engine;

revoke all on engine.audit_logs from anon, authenticated;

comment on table engine.audit_logs is
  'Server-side provenance for operator and agent actions. Written by '
  'db.audit(); not yet read by any surface (see header).';
