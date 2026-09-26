-- 0007: PII vault + Lead projection (projects context).
-- The vault holds ONLY ciphertext; business tables hold refs + masked values.
-- The lead projection is a rebuildable read model, never the source of truth.

CREATE SCHEMA IF NOT EXISTS pii;
CREATE SCHEMA IF NOT EXISTS projects;

CREATE TABLE pii.deks (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id       uuid NOT NULL REFERENCES platform.organizations(id),
  wrapped_dek  bytea NOT NULL,
  alg          text NOT NULL DEFAULT 'AES-256-GCM',
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_deks_org ON pii.deks (org_id);

CREATE TABLE pii.vault (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL REFERENCES platform.organizations(id),
  kind        text NOT NULL CHECK (kind IN ('email','phone')),
  ciphertext  bytea NOT NULL,
  iv          bytea NOT NULL,
  dek_id      uuid NOT NULL REFERENCES pii.deks(id),
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_vault_org ON pii.vault (org_id);

CREATE TABLE pii.pii_access_audit (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id       uuid NOT NULL REFERENCES platform.organizations(id),
  ref_id       uuid NOT NULL REFERENCES pii.vault(id),
  purpose      text NOT NULL CHECK (purpose IN ('verification','outreach','human_review','legal_request')),
  actor        text NOT NULL,
  service      text NOT NULL DEFAULT 'lead-engine-v6',
  request_id   text,
  accessed_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_pii_audit_ref ON pii.pii_access_audit (ref_id);

-- Lead projection: rebuilt from authoritative data by application code.
CREATE TABLE projects.lead_projections (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id                uuid NOT NULL REFERENCES platform.organizations(id),
  campaign_id           uuid REFERENCES acquisition.campaigns(id),
  company_id            uuid NOT NULL REFERENCES company_identity.companies(id),
  contact_id            uuid REFERENCES contacts.company_contacts(id),
  icp_version_id        uuid REFERENCES acquisition.icp_versions(id),
  display               jsonb NOT NULL,
  masked_email          text,
  masked_phone          text,
  email_status          text,
  score                 numeric,
  score_version         text,
  decision              text,
  state                 text NOT NULL DEFAULT 'READY_FOR_REVIEW'
                        CHECK (state IN ('READY_FOR_REVIEW','APPROVED','REJECTED')),
  built_from            jsonb NOT NULL DEFAULT '{}'::jsonb,
  built_at              timestamptz NOT NULL DEFAULT now(),
  UNIQUE (org_id, campaign_id, company_id, contact_id)
);
CREATE INDEX idx_leads_org ON projects.lead_projections (org_id, built_at DESC);
CREATE INDEX idx_leads_state ON projects.lead_projections (org_id, state);

ALTER TABLE pii.deks              ENABLE ROW LEVEL SECURITY;
ALTER TABLE pii.deks              FORCE ROW LEVEL SECURITY;
ALTER TABLE pii.vault             ENABLE ROW LEVEL SECURITY;
ALTER TABLE pii.vault             FORCE ROW LEVEL SECURITY;
ALTER TABLE pii.pii_access_audit  ENABLE ROW LEVEL SECURITY;
ALTER TABLE pii.pii_access_audit  FORCE ROW LEVEL SECURITY;
ALTER TABLE projects.lead_projections ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects.lead_projections FORCE ROW LEVEL SECURITY;

CREATE POLICY deks_tenant ON pii.deks
  USING (org_id = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK (org_id = current_setting('app.tenant_id', true)::uuid);
CREATE POLICY vault_tenant ON pii.vault
  USING (org_id = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK (org_id = current_setting('app.tenant_id', true)::uuid);
CREATE POLICY pii_audit_tenant ON pii.pii_access_audit
  USING (org_id = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK (org_id = current_setting('app.tenant_id', true)::uuid);
CREATE POLICY leads_tenant ON projects.lead_projections
  USING (org_id = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK (org_id = current_setting('app.tenant_id', true)::uuid);
