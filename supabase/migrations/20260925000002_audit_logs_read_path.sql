-- ============================================================
-- Migration — engine.audit_logs: read-path index + retention posture
--
-- Context: 20260925000001 made the table writable. This migration ships with
-- the first READER: GET /api/audit (lead_engine/activity/store.py
-- AuditTrailStore). Every read this surface implements has one shape:
--
--   SELECT id, organization_id, actor, action, entity_type, entity_id,
--          payload_json, created_at
--     FROM audit_logs
--    WHERE organization_id = <tenant>            -- or the platform predicate
--      [AND id < <before_id>] [AND actor/action/entity_type/entity_id = ...]
--      [AND created_at BETWEEN <from> AND <to>]
--    ORDER BY id DESC
--    LIMIT <n> OFFSET <k>
--
-- One statement per page; no per-row round trips, no joins, no jsonb operator
-- in SQL (payload is parsed in Python so the identical query works against
-- SQLite's TEXT mirror too — dialect parity, see tests/test_audit_trail.py).
--
-- Why a new index: the existing audit_logs_org_created_idx
-- (organization_id, created_at DESC) cannot serve this access pattern.
-- Sorting happens on `id`, not created_at, for two reasons:
--   1. created_at is written by the app at SECOND precision (db.utcnow()
--      truncates), so an operator batch of decisions ties within one second.
--      ORDER BY created_at DESC is not a total order, and LIMIT/OFFSET over
--      ties duplicates or drops rows between pages. id (identity) is
--      monotonic and unique: a stable keyset cursor (before_id).
--   2. The planner needs (organization_id, id DESC) to walk the tenant slice
--      newest-first and stop at LIMIT; without it every timeline read is a
--      full tenant scan + sort.
create index if not exists audit_logs_org_id_idx
  on engine.audit_logs (organization_id, id desc);

-- Per-entity provenance (?entity_type=lead&entity_id=...) is served by the
-- existing audit_logs_entity_idx (entity_type, entity_id): an entity's action
-- history is a handful of rows, org-filtered and id-sorted post-fetch without
-- a measurable cost. No further index until observed otherwise — an audit
-- table is insert-heavy, and every unused index is write amplification.

-- ------------------------------------------------------------ retention
-- Policy as implemented: audit rows are retained INDEFINITELY. There is NO
-- deletion, TRUNCATE, or TTL anywhere in this migration or in the application
-- read path, and none is planned without an explicit owner decision — the
-- payload column legitimately carries the operator's identity (sub/email) and
-- the data subject's identifier (lead entity_id), so erasure is an unresolved
-- compliance question (record-retention duty vs data-subject erasure), not an
-- engineering oversight.
--
-- What the schema already supports for the future decision, without code:
--   * time-windowed reads: created_at timestamptz + this table's insert-
--     monotonic id mean an archival job can select or detach a closed range
--     (created_at < now() - interval '...' AND id <= <watermark>) without
--     scanning live data; if a retention horizon is ever set, implement it as
--     a scheduled migration-owned DELETE or monthly partition detach, never
--     from the app role (which holds SELECT+INSERT only — see 20260925000001
--     grants; this migration adds none).
--   * a redaction path (UPDATE payload_json keeping actor/action skeleton) is
--     deliberately NOT built here; see the task report.
--
-- RLS note: engine.audit_logs stays OUTSIDE forced row-level security on
-- purpose. The write path (db.audit / codeops.audit) must never fail — a
-- rejected audit INSERT after a committed mutation is the exact outage
-- 20260925000001 ended — and a sentinel ('__no_org__') context has no org GUC
-- to satisfy a WITH CHECK policy. Read isolation therefore lives in
-- AuditTrailStore's tenant predicate (fail-closed; stricter than the
-- activity feed: no cross-tenant NULL-row visibility). Whether audit_logs
-- should get RLS with a dedicated writer exemption is an owner decision.
comment on table engine.audit_logs is
  'Server-side provenance for operator and agent actions. Written by '
  'db.audit()/codeops.audit(); read by GET /api/audit via tenant-scoped '
  'single-statement pages. Retained indefinitely; no deletion path exists.';
