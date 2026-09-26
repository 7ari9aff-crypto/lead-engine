# ADR-0002 — Supabase managed Postgres

Status: accepted

Supabase stays the managed Postgres provider. V6 connects with plain `psycopg`
over `LEAD_ENGINE_V6_DATABASE_URL` — no Supabase SDK in domain/application code.
RLS is enforced with `FORCE ROW LEVEL SECURITY` plus `SET LOCAL app.tenant_id`
per transaction (pooler-safe). Migrations are plain SQL applied by our runner,
not by hand in the SQL editor (the legacy drift that lost `public.webhooks`
and `public.suppression_entries` must never recur).
