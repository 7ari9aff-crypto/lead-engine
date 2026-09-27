-- 0011: Ensure the application role exists on any Postgres.
-- On Supabase the lead_engine role pre-exists (restricted DML role); on plain
-- Postgres (CI service container, local dev) it is created here so migration
-- 0009 grants apply everywhere.

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'lead_engine') THEN
    CREATE ROLE lead_engine NOLOGIN;
  END IF;
END $$;
