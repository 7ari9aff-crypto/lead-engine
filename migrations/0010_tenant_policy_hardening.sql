-- 0010: Harden tenant isolation policies (fail-closed).
-- Footgun being fixed: after the first SET LOCAL app.tenant_id in a pooled
-- session, current_setting('app.tenant_id', true) returns '' (not NULL) in
-- later transactions, which made ''::uuid raise instead of deny. All tenant
-- policies now resolve through app_tenant_uuid(): NULL for unset/empty →
-- every predicate false → deny.

CREATE OR REPLACE FUNCTION public.app_tenant_uuid() RETURNS uuid
LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid
$$;

DO $$
DECLARE
  t record;
BEGIN
  -- drop every existing policy on tenant-owned tables
  FOR t IN
    SELECT schemaname, tablename, policyname FROM pg_policies
    WHERE schemaname IN ('platform', 'acquisition', 'company_identity',
                         'claims_evidence', 'contacts', 'intelligence',
                         'governance', 'projects', 'pii')
  LOOP
    EXECUTE format('DROP POLICY %I ON %I.%I', t.policyname, t.schemaname, t.tablename);
  END LOOP;

  -- recreate uniformly: every table with an org_id column
  FOR t IN
    SELECT DISTINCT c.table_schema AS s, c.table_name AS tbl
    FROM information_schema.columns c
    WHERE c.table_schema IN ('platform', 'acquisition', 'company_identity',
                             'claims_evidence', 'contacts', 'intelligence',
                             'governance', 'projects', 'pii')
      AND c.column_name = 'org_id'
      AND EXISTS (SELECT 1 FROM information_schema.tables x
                   WHERE x.table_schema = c.table_schema
                     AND x.table_name = c.table_name AND x.table_type = 'BASE TABLE')
  LOOP
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I.%I USING (%I = public.app_tenant_uuid())'
      ' WITH CHECK (%I = public.app_tenant_uuid())',
      t.s, t.tbl, 'org_id', 'org_id');
  END LOOP;

  -- organizations: tenant column is its own id
  EXECUTE 'CREATE POLICY tenant_isolation ON platform.organizations
           USING (id = public.app_tenant_uuid()) WITH CHECK (id = public.app_tenant_uuid())';
END $$;
