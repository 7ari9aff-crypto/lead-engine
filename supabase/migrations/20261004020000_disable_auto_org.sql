-- 20261004020000_disable_auto_org.sql
-- Signup ≠ organization creation (decision 2026-10-04).
--
-- handle_new_user_org() used to create an organization + owner membership
-- for EVERY new auth user: an open signup then minted tenants (and owners)
-- in bulk, disconnected from any onboarding or approval. Organizations are
-- now created/joined explicitly through onboarding (v6
-- /api/v1/platform/onboard, or the legacy admin path). The trigger stays in
-- place as a no-op so the provisioning hook point survives for any future
-- user-scoped (non-tenant) provisioning.

create or replace function public.handle_new_user_org()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  -- Intentionally no longer creates an organization. Signup must never
  -- mint tenants; onboarding owns that boundary.
  return new;
end;
$$;
