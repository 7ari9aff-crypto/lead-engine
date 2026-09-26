-- 0004: Claims & Evidence + Contact contexts.
-- Invariants: Observation ≠ Truth, Claim ≠ Source, Source ≠ Qualification.
-- Contact PII is stored only as references into the PII vault (0007).

CREATE SCHEMA IF NOT EXISTS claims_evidence;
CREATE SCHEMA IF NOT EXISTS contacts;

CREATE TABLE claims_evidence.fact_sources (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id        uuid NOT NULL REFERENCES platform.organizations(id),
  kind          text NOT NULL CHECK (kind IN ('search_result','web_page','provider','human')),
  url           text,
  provider_id   text,
  content_hash  text,
  fetched_at    timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_source_hash ON claims_evidence.fact_sources (org_id, content_hash)
  WHERE content_hash IS NOT NULL;

CREATE TABLE claims_evidence.company_observations (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id            uuid NOT NULL REFERENCES platform.organizations(id),
  company_id        uuid NOT NULL REFERENCES company_identity.companies(id),
  field             text NOT NULL,
  value             text,
  source_id         uuid REFERENCES claims_evidence.fact_sources(id),
  extraction_method text NOT NULL DEFAULT 'snippet',
  confidence        numeric NOT NULL DEFAULT 0.5,
  collected_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_observations_company ON claims_evidence.company_observations (company_id, field);

CREATE TABLE claims_evidence.company_claims (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id            uuid NOT NULL REFERENCES platform.organizations(id),
  company_id        uuid NOT NULL REFERENCES company_identity.companies(id),
  field             text NOT NULL,
  value             text,
  source_id         uuid REFERENCES claims_evidence.fact_sources(id),
  extraction_method text NOT NULL,
  confidence        numeric NOT NULL DEFAULT 0.5,
  truth_state       text NOT NULL DEFAULT 'proposed'
                    CHECK (truth_state IN ('proposed','verified','conflicted','retired')),
  collected_at      timestamptz NOT NULL DEFAULT now(),
  verified_at       timestamptz
);
CREATE UNIQUE INDEX uq_claim_current
  ON claims_evidence.company_claims (org_id, company_id, field)
  WHERE truth_state IN ('proposed','verified','conflicted');
CREATE INDEX idx_claims_company ON claims_evidence.company_claims (company_id);

CREATE TABLE claims_evidence.fact_conflicts (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id        uuid NOT NULL REFERENCES platform.organizations(id),
  company_id    uuid NOT NULL REFERENCES company_identity.companies(id),
  field         text NOT NULL,
  claim_a_id    uuid NOT NULL REFERENCES claims_evidence.company_claims(id),
  claim_b_id    uuid NOT NULL REFERENCES claims_evidence.company_claims(id),
  state         text NOT NULL DEFAULT 'open' CHECK (state IN ('open','resolved')),
  created_at    timestamptz NOT NULL DEFAULT now(),
  resolved_at   timestamptz
);

CREATE TABLE contacts.company_contacts (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id        uuid NOT NULL REFERENCES platform.organizations(id),
  company_id    uuid NOT NULL REFERENCES company_identity.companies(id),
  name          text,
  role          text,
  source_id     uuid REFERENCES claims_evidence.fact_sources(id),
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_contacts_identity
  ON contacts.company_contacts (org_id, company_id, role, lower(name));
CREATE INDEX idx_contacts_company ON contacts.company_contacts (company_id);

CREATE TABLE contacts.contact_identities (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id       uuid NOT NULL REFERENCES platform.organizations(id),
  contact_id   uuid NOT NULL REFERENCES contacts.company_contacts(id),
  kind         text NOT NULL CHECK (kind IN ('email','phone','social')),
  public_value text,              -- social links only; email/phone are PII
  pii_ref_id   uuid,              -- into pii.vault (0007); never plaintext
  UNIQUE (contact_id, kind, public_value, pii_ref_id)
);

ALTER TABLE claims_evidence.fact_sources           ENABLE ROW LEVEL SECURITY;
ALTER TABLE claims_evidence.fact_sources           FORCE ROW LEVEL SECURITY;
ALTER TABLE claims_evidence.company_observations   ENABLE ROW LEVEL SECURITY;
ALTER TABLE claims_evidence.company_observations   FORCE ROW LEVEL SECURITY;
ALTER TABLE claims_evidence.company_claims         ENABLE ROW LEVEL SECURITY;
ALTER TABLE claims_evidence.company_claims         FORCE ROW LEVEL SECURITY;
ALTER TABLE claims_evidence.fact_conflicts         ENABLE ROW LEVEL SECURITY;
ALTER TABLE claims_evidence.fact_conflicts         FORCE ROW LEVEL SECURITY;
ALTER TABLE contacts.company_contacts              ENABLE ROW LEVEL SECURITY;
ALTER TABLE contacts.company_contacts              FORCE ROW LEVEL SECURITY;
ALTER TABLE contacts.contact_identities            ENABLE ROW LEVEL SECURITY;
ALTER TABLE contacts.contact_identities            FORCE ROW LEVEL SECURITY;

CREATE POLICY sources_tenant ON claims_evidence.fact_sources
  USING (org_id = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK (org_id = current_setting('app.tenant_id', true)::uuid);
CREATE POLICY observations_tenant ON claims_evidence.company_observations
  USING (org_id = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK (org_id = current_setting('app.tenant_id', true)::uuid);
CREATE POLICY claims_tenant ON claims_evidence.company_claims
  USING (org_id = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK (org_id = current_setting('app.tenant_id', true)::uuid);
CREATE POLICY conflicts_tenant ON claims_evidence.fact_conflicts
  USING (org_id = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK (org_id = current_setting('app.tenant_id', true)::uuid);
CREATE POLICY contacts_tenant ON contacts.company_contacts
  USING (org_id = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK (org_id = current_setting('app.tenant_id', true)::uuid);
CREATE POLICY contact_identities_tenant ON contacts.contact_identities
  USING (org_id = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK (org_id = current_setting('app.tenant_id', true)::uuid);
