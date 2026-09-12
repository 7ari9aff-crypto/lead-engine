-- 20260911000007_rls_engine.sql
-- Defense-in-depth tenant isolation at the DATABASE layer (audit #4):
-- every engine table that carries organization_id gets RLS FORCED with a
-- single tenant policy driven by the app.current_org session setting.
--
-- The application connects as the lead_engine role (NOBYPASSRLS) and sets
--   SET app.current_org = '<org uuid>'
-- on each connection. Superuser (migrations only) bypasses RLS by design.
--
-- Policy semantics:
--   org set     -> rows of that org + platform rows (organization_id IS NULL)
--   org unset   -> platform rows only, and inserts must carry NULL org
--                  (fail-closed: a tenant write without context is rejected)

do $$
declare
  t text;
begin
  -- the role the application runs as
  execute 'grant usage on schema engine to lead_engine';
  execute 'grant select, insert, update, delete on all tables in schema engine to lead_engine';
  execute 'grant usage, select on all sequences in schema engine to lead_engine';
  execute 'alter default privileges in schema engine'
          ' grant select, insert, update, delete on tables to lead_engine';
  execute 'alter default privileges in schema engine'
          ' grant usage, select on sequences to lead_engine';

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
        or organization_id is null
      )
      with check (
        organization_id::text = coalesce(current_setting('app.current_org', true), '')
        or organization_id is null
      )
    $p$, t);
  end loop;
end $$;
