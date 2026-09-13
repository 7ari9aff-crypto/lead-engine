-- 20260913000002_truth_rls_tighten.sql
-- Review fix (R1 audit): facts and ICP versions are ALWAYS tenant data —
-- unlike the engine tables from migration 007, these get NO NULL-org escape
-- hatch in WITH CHECK. A write without an org context is rejected outright
-- (fail-closed), and NULL-org rows would be invisible to tenants even if a
-- bug ever created one.

do $$
declare t text;
begin
  foreach t in array array['research_facts','fact_sources','fact_conflicts',
                           'open_questions','visited_sources','icp_versions']
  loop
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
end $$;

-- platform-safe uniqueness for icp_versions (NULL-org rows could previously
-- duplicate the same slug+version because NULLs are distinct in unique
-- constraints — the coalesce index closes that, same pattern as research_facts)
create unique index if not exists uq_icp_org_slug_version
  on engine.icp_versions
  (coalesce(organization_id, '00000000-0000-0000-0000-000000000000'::uuid),
   slug, version);
