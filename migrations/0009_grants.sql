-- 0009: Grants for the application role (lead_engine) on all V6 schemas.
-- Applied by the postgres role via the migration runner; makes the runtime
-- role able to do DML everywhere in V6 while DDL stays migration-only.
-- RLS still applies to lead_engine (non-owner) on every tenant table.

GRANT USAGE ON SCHEMA platform, acquisition, company_identity, claims_evidence,
  contacts, intelligence, governance, projects, pii, runtime, events, effects, agents
  TO lead_engine;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA
  platform, acquisition, company_identity, claims_evidence,
  contacts, intelligence, governance, projects, pii, runtime, events, effects, agents
  TO lead_engine;

GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA
  platform, acquisition, company_identity, claims_evidence,
  contacts, intelligence, governance, projects, pii, runtime, events, effects, agents
  TO lead_engine;

ALTER DEFAULT PRIVILEGES IN SCHEMA platform, acquisition, company_identity, claims_evidence,
  contacts, intelligence, governance, projects, pii, runtime, events, effects, agents
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO lead_engine;

ALTER DEFAULT PRIVILEGES IN SCHEMA platform, acquisition, company_identity, claims_evidence,
  contacts, intelligence, governance, projects, pii, runtime, events, effects, agents
  GRANT USAGE, SELECT ON SEQUENCES TO lead_engine;

GRANT SELECT ON runtime.schema_migrations TO lead_engine;
