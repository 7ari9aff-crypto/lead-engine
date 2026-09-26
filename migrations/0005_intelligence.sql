-- 0005: Intelligence context — discovery artifacts, enrichment, verification,
-- scoring, qualification, intent. Historical records are never overwritten.

CREATE SCHEMA IF NOT EXISTS intelligence;

CREATE TABLE intelligence.raw_discovery_results (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id        uuid NOT NULL REFERENCES platform.organizations(id),
  job_id        uuid,
  provider_id   text NOT NULL,
  query         text NOT NULL,
  url           text NOT NULL,
  title         text,
  snippet       text,
  fetched_at    timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_raw_result ON intelligence.raw_discovery_results (org_id, job_id, url);

CREATE TABLE intelligence.visited_sources (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL REFERENCES platform.organizations(id),
  job_id      uuid,
  url         text NOT NULL,
  url_hash    text NOT NULL,
  visited_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (org_id, url_hash)
);

CREATE TABLE intelligence.enrichment_attempts (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id         uuid NOT NULL REFERENCES platform.organizations(id),
  company_id     uuid NOT NULL REFERENCES company_identity.companies(id),
  provider_id    text NOT NULL,
  operation      text NOT NULL,
  status         text NOT NULL CHECK (status IN ('ok','failed','skipped')),
  failure_class  text,
  cost_cents     numeric NOT NULL DEFAULT 0,
  effect_id      uuid,
  created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_enrich_company ON intelligence.enrichment_attempts (company_id);

CREATE TABLE intelligence.verification_records (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id        uuid NOT NULL REFERENCES platform.organizations(id),
  contact_id    uuid NOT NULL REFERENCES contacts.company_contacts(id),
  kind          text NOT NULL CHECK (kind IN ('email','phone')),
  pii_ref_id    uuid,
  status        text NOT NULL
                CHECK (status IN ('DELIVERABLE','RISKY','CATCH_ALL','INVALID','UNKNOWN')),
  provider_id   text,
  evidence      jsonb NOT NULL DEFAULT '{}'::jsonb,
  verified_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_verification_contact ON intelligence.verification_records (contact_id);

CREATE TABLE intelligence.verification_cache (
  org_id      uuid NOT NULL REFERENCES platform.organizations(id),
  cache_key   text NOT NULL,
  status      text NOT NULL,
  evidence    jsonb NOT NULL DEFAULT '{}'::jsonb,
  expires_at  timestamptz NOT NULL,
  PRIMARY KEY (org_id, cache_key)
);

CREATE TABLE intelligence.scoring_records (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          uuid NOT NULL REFERENCES platform.organizations(id),
  company_id      uuid NOT NULL REFERENCES company_identity.companies(id),
  score           numeric NOT NULL,
  score_version   text NOT NULL,
  input_snapshot  jsonb NOT NULL,
  explanations    jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_scoring_company ON intelligence.scoring_records (company_id, created_at DESC);

CREATE TABLE intelligence.qualification_records (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id           uuid NOT NULL REFERENCES platform.organizations(id),
  company_id       uuid NOT NULL REFERENCES company_identity.companies(id),
  campaign_id      uuid REFERENCES acquisition.campaigns(id),
  decision         text NOT NULL CHECK (decision IN ('accepted','review','rejected')),
  reasons          jsonb NOT NULL DEFAULT '[]'::jsonb,
  icp_version_id   uuid REFERENCES acquisition.icp_versions(id),
  policy_version   text NOT NULL DEFAULT 'default-v1',
  created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_qualification_company ON intelligence.qualification_records (company_id);

CREATE TABLE intelligence.intent_signals (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id        uuid NOT NULL REFERENCES platform.organizations(id),
  company_id    uuid NOT NULL REFERENCES company_identity.companies(id),
  kind          text NOT NULL,
  signal        text NOT NULL,
  source_id     uuid REFERENCES claims_evidence.fact_sources(id),
  collected_at  timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE intelligence.raw_discovery_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE intelligence.raw_discovery_results FORCE ROW LEVEL SECURITY;
ALTER TABLE intelligence.visited_sources       ENABLE ROW LEVEL SECURITY;
ALTER TABLE intelligence.visited_sources       FORCE ROW LEVEL SECURITY;
ALTER TABLE intelligence.enrichment_attempts   ENABLE ROW LEVEL SECURITY;
ALTER TABLE intelligence.enrichment_attempts   FORCE ROW LEVEL SECURITY;
ALTER TABLE intelligence.verification_records  ENABLE ROW LEVEL SECURITY;
ALTER TABLE intelligence.verification_records  FORCE ROW LEVEL SECURITY;
ALTER TABLE intelligence.verification_cache    ENABLE ROW LEVEL SECURITY;
ALTER TABLE intelligence.verification_cache    FORCE ROW LEVEL SECURITY;
ALTER TABLE intelligence.scoring_records       ENABLE ROW LEVEL SECURITY;
ALTER TABLE intelligence.scoring_records       FORCE ROW LEVEL SECURITY;
ALTER TABLE intelligence.qualification_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE intelligence.qualification_records FORCE ROW LEVEL SECURITY;
ALTER TABLE intelligence.intent_signals        ENABLE ROW LEVEL SECURITY;
ALTER TABLE intelligence.intent_signals        FORCE ROW LEVEL SECURITY;

CREATE POLICY raw_results_tenant ON intelligence.raw_discovery_results
  USING (org_id = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK (org_id = current_setting('app.tenant_id', true)::uuid);
CREATE POLICY visited_tenant ON intelligence.visited_sources
  USING (org_id = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK (org_id = current_setting('app.tenant_id', true)::uuid);
CREATE POLICY enrichment_tenant ON intelligence.enrichment_attempts
  USING (org_id = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK (org_id = current_setting('app.tenant_id', true)::uuid);
CREATE POLICY verification_tenant ON intelligence.verification_records
  USING (org_id = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK (org_id = current_setting('app.tenant_id', true)::uuid);
CREATE POLICY verification_cache_tenant ON intelligence.verification_cache
  USING (org_id = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK (org_id = current_setting('app.tenant_id', true)::uuid);
CREATE POLICY scoring_tenant ON intelligence.scoring_records
  USING (org_id = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK (org_id = current_setting('app.tenant_id', true)::uuid);
CREATE POLICY qualification_tenant ON intelligence.qualification_records
  USING (org_id = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK (org_id = current_setting('app.tenant_id', true)::uuid);
CREATE POLICY intent_tenant ON intelligence.intent_signals
  USING (org_id = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK (org_id = current_setting('app.tenant_id', true)::uuid);
