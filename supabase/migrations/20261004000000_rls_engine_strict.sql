-- 20261004000000_rls_engine_strict.sql
-- Close the NULL-org escape hatch in the engine.* tenant policies.
--
-- 20260911000007_rls_engine.sql granted every tenant visibility of rows with
-- organization_id IS NULL ("platform rows"). But leads/jobs/usage are NOT
-- platform rows: a NULL-org lead written by an org-less code path was visible
-- AND writable by every tenant. The write path that could produce such rows
-- (api_jobs_start background task opening its own DB handle without an org)
-- is fixed in code; this migration removes the door itself. Current NULL-org
-- row count: 0 (verified before applying).
--
-- System-plane schemas (runtime, events, effects, agents) deliberately keep
-- NO RLS: they are the cross-tenant execution plane (leasing, outbox, effect
-- ledger) — their org_id columns are ATTRIBUTION, not isolation, and the
-- worker/system queries must see all tenants. Isolation for their reads is
-- enforced in the API layer (every read is org-filtered or admin-gated).
-- platform.members stays RLS-off deliberately too: it is the identity plane
-- resolved BEFORE a tenant context exists.

do $$
declare
  t text;
begin
  for t in
    select c.table_name::text
    from information_schema.columns c
    where c.table_schema = 'engine' and c.column_name = 'organization_id'
  loop
    execute format('alter table engine.%I enable row level security', t);
    execute format('alter table engine.%I force row level security', t);

    execute format('drop policy if exists tenant_isolation on engine.%I', t);
    execute format($p$
      create policy tenant_isolation on engine.%I
      using (
        organization_id::text = coalesce(current_setting('app.current_org', true), '')
      )
      with check (
        organization_id::text = coalesce(current_setting('app.current_org', true), '')
      )
    $p$, t);
  end loop;

  -- platform.feature_flags carries org_id and is tenant-owned: enable the
  -- tenant_isolation policy 0010 already created (it was inert without this).
  alter table platform.feature_flags enable row level security;
  alter table platform.feature_flags force row level security;
end $$;
