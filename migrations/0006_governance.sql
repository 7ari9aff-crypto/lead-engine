-- 0006: Governance context — legal policies, decisions, suppression, privacy.
-- Governance is a hard gate: pipeline phases must evaluate policy and record
-- an immutable decision before proceeding on regulated/outbound operations.

CREATE SCHEMA IF NOT EXISTS governance;

CREATE TABLE governance.legal_policy_versions (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id        uuid NOT NULL REFERENCES platform.organizations(id),
  name          text NOT NULL DEFAULT 'default',
  version       text NOT NULL,
  rules         jsonb NOT NULL,
  published_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (org_id, name, version)
);

CREATE TABLE governance.legal_decisions (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id           uuid NOT NULL REFERENCES platform.organizations(id),
  subject_type     text NOT NULL,
  subject_id       text NOT NULL,
  operation        text NOT NULL,
  decision         text NOT NULL CHECK (decision IN ('ALLOWED','BLOCKED','NEEDS_REVIEW')),
  policy_version   text NOT NULL,
  legal_basis      text,
  decision_reason  text,
  decided_by       text NOT NULL DEFAULT 'policy-engine',
  created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_legal_decisions_subject ON governance.legal_decisions (org_id, subject_type, subject_id);

CREATE TABLE governance.suppression (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL REFERENCES platform.organizations(id),
  kind        text NOT NULL CHECK (kind IN ('email','domain','company','contact')),
  value       text NOT NULL,
  reason      text NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (org_id, kind, value)
);

CREATE TABLE governance.privacy_actions (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id        uuid NOT NULL REFERENCES platform.organizations(id),
  action        text NOT NULL CHECK (action IN ('erase','export','restrict')),
  subject_type  text NOT NULL,
  subject_id    text NOT NULL,
  performed_by  text NOT NULL,
  detail        jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at    timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE governance.legal_policy_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE governance.legal_policy_versions FORCE ROW LEVEL SECURITY;
ALTER TABLE governance.legal_decisions       ENABLE ROW LEVEL SECURITY;
ALTER TABLE governance.legal_decisions       FORCE ROW LEVEL SECURITY;
ALTER TABLE governance.suppression           ENABLE ROW LEVEL SECURITY;
ALTER TABLE governance.suppression           FORCE ROW LEVEL SECURITY;
ALTER TABLE governance.privacy_actions       ENABLE ROW LEVEL SECURITY;
ALTER TABLE governance.privacy_actions       FORCE ROW LEVEL SECURITY;

CREATE POLICY policy_versions_tenant ON governance.legal_policy_versions
  USING (org_id = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK (org_id = current_setting('app.tenant_id', true)::uuid);
CREATE POLICY decisions_tenant ON governance.legal_decisions
  USING (org_id = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK (org_id = current_setting('app.tenant_id', true)::uuid);
CREATE POLICY suppression_tenant ON governance.suppression
  USING (org_id = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK (org_id = current_setting('app.tenant_id', true)::uuid);
CREATE POLICY privacy_tenant ON governance.privacy_actions
  USING (org_id = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK (org_id = current_setting('app.tenant_id', true)::uuid);
