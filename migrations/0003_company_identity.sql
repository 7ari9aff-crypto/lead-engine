-- 0003: Company Identity context. Company is canonical business truth;
-- merge history is append-only (never deleted).

CREATE SCHEMA IF NOT EXISTS company_identity;

CREATE TABLE company_identity.companies (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          uuid NOT NULL REFERENCES platform.organizations(id),
  canonical_name  text NOT NULL,
  domain          text,
  country         text,
  industry        text,
  city            text,
  merged_into_id  uuid REFERENCES company_identity.companies(id),
  created_at      timestamptz NOT NULL DEFAULT now()
);
-- identity anchor: one live company per (org, domain)
CREATE UNIQUE INDEX uq_company_domain
  ON company_identity.companies (org_id, lower(domain))
  WHERE domain IS NOT NULL AND merged_into_id IS NULL;
CREATE INDEX idx_company_name ON company_identity.companies (org_id, lower(canonical_name));

CREATE TABLE company_identity.company_identifiers (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL REFERENCES platform.organizations(id),
  company_id  uuid NOT NULL REFERENCES company_identity.companies(id),
  kind        text NOT NULL CHECK (kind IN ('domain','name','phone','social')),
  value       text NOT NULL,
  source_id   uuid,
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (org_id, kind, value)
);
CREATE INDEX idx_identifiers_company ON company_identity.company_identifiers (company_id);

CREATE TABLE company_identity.company_merges (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id           uuid NOT NULL REFERENCES platform.organizations(id),
  from_company_id  uuid NOT NULL REFERENCES company_identity.companies(id),
  into_company_id  uuid NOT NULL REFERENCES company_identity.companies(id),
  reason           text NOT NULL,
  created_at       timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE company_identity.companies           ENABLE ROW LEVEL SECURITY;
ALTER TABLE company_identity.companies           FORCE ROW LEVEL SECURITY;
ALTER TABLE company_identity.company_identifiers ENABLE ROW LEVEL SECURITY;
ALTER TABLE company_identity.company_identifiers FORCE ROW LEVEL SECURITY;
ALTER TABLE company_identity.company_merges      ENABLE ROW LEVEL SECURITY;
ALTER TABLE company_identity.company_merges      FORCE ROW LEVEL SECURITY;

CREATE POLICY companies_tenant ON company_identity.companies
  USING (org_id = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK (org_id = current_setting('app.tenant_id', true)::uuid);
CREATE POLICY identifiers_tenant ON company_identity.company_identifiers
  USING (org_id = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK (org_id = current_setting('app.tenant_id', true)::uuid);
CREATE POLICY merges_tenant ON company_identity.company_merges
  USING (org_id = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK (org_id = current_setting('app.tenant_id', true)::uuid);
