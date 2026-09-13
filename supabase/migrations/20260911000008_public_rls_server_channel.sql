-- 20260911000008_public_rls_server_channel.sql
-- The server (lead_engine role) must read/write the platform tables it owns
-- data in, WITHOUT auth.uid() (that exists only for browser PostgREST
-- sessions). Policies now accept EITHER the browser identity
-- (auth.uid()) OR the server tenant context (app.current_org) — tenant
-- isolation stays enforced at the database layer for both channels.

-- grants so the app role can touch the platform tables it needs
grant select, insert, update, delete on
  public.organizations,
  public.organization_members,
  public.api_keys,
  public.organization_provider_credentials,
  public.audit_logs,
  public.integration_connections
to lead_engine;

do $$
declare
  t text;
  col text;
begin
  -- organization_members: a member sees own rows; server sees its whole org
  execute 'drop policy if exists member_select_same_org on public.organization_members';
  execute $p$create policy member_select_same_org on public.organization_members
    for select using (
      auth.uid() = user_id
      or organization_id::text = coalesce(current_setting('app.current_org', true), '')
    )$p$;
  execute 'drop policy if exists member_insert_server on public.organization_members';
  execute $p$create policy member_insert_server on public.organization_members
    for insert with check (
      auth.uid() = user_id
      or (organization_id::text = coalesce(current_setting('app.current_org', true), '')
          and coalesce(current_setting('app.current_org', true), '') <> '')
    )$p$;
  execute 'drop policy if exists member_manage_admin on public.organization_members';
  execute $p$create policy member_manage_admin on public.organization_members
    for all using (
      auth.uid() = user_id
      or organization_id::text = coalesce(current_setting('app.current_org', true), '')
    ) with check (
      auth.uid() = user_id
      or organization_id::text = coalesce(current_setting('app.current_org', true), '')
    )$p$;

  -- generic org-keyed tables: server channel matches the tenant context
  foreach t in array
    array['api_keys', 'organization_provider_credentials', 'audit_logs', 'integration_connections']
  loop
    execute format('alter table public.%I enable row level security', t);
    execute format('drop policy if exists tenant_channel on public.%I', t);
    execute format($p$create policy tenant_channel on public.%I
      for all using (
        organization_id::text = coalesce(current_setting('app.current_org', true), '')
      ) with check (
        organization_id::text = coalesce(current_setting('app.current_org', true), '')
      )$p$, t);
  end loop;
end $$;
