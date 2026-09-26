-- 0002: Campaign & ICP context. ICP versions are immutable after publish
-- (enforced by trigger), satisfying the locked invariant.

CREATE SCHEMA IF NOT EXISTS acquisition;

CREATE TABLE acquisition.icp_profiles (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL REFERENCES platform.organizations(id),
  name        text NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE acquisition.icp_versions (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id        uuid NOT NULL REFERENCES platform.organizations(id),
  profile_id    uuid NOT NULL REFERENCES acquisition.icp_profiles(id),
  version       int  NOT NULL,
  definition    jsonb NOT NULL,
  published_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (profile_id, version)
);

CREATE FUNCTION acquisition.icp_versions_immutable() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'icp version % is immutable', OLD.id;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_icp_versions_immutable
  BEFORE UPDATE OR DELETE ON acquisition.icp_versions
  FOR EACH ROW EXECUTE FUNCTION acquisition.icp_versions_immutable();

CREATE TABLE acquisition.campaigns (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          uuid NOT NULL REFERENCES platform.organizations(id),
  name            text NOT NULL,
  icp_version_id  uuid NOT NULL REFERENCES acquisition.icp_versions(id),
  state           text NOT NULL DEFAULT 'DRAFT'
                  CHECK (state IN ('DRAFT','RUNNING','READY_FOR_REVIEW','COMPLETED','CANCELLED','FAILED')),
  budget_cents    int NOT NULL DEFAULT 0,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_campaigns_org ON acquisition.campaigns (org_id, created_at DESC);

ALTER TABLE acquisition.icp_profiles   ENABLE ROW LEVEL SECURITY;
ALTER TABLE acquisition.icp_profiles   FORCE ROW LEVEL SECURITY;
ALTER TABLE acquisition.icp_versions   ENABLE ROW LEVEL SECURITY;
ALTER TABLE acquisition.icp_versions   FORCE ROW LEVEL SECURITY;
ALTER TABLE acquisition.campaigns      ENABLE ROW LEVEL SECURITY;
ALTER TABLE acquisition.campaigns      FORCE ROW LEVEL SECURITY;

CREATE POLICY icp_profiles_tenant ON acquisition.icp_profiles
  USING (org_id = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK (org_id = current_setting('app.tenant_id', true)::uuid);
CREATE POLICY icp_versions_tenant ON acquisition.icp_versions
  USING (org_id = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK (org_id = current_setting('app.tenant_id', true)::uuid);
CREATE POLICY campaigns_tenant ON acquisition.campaigns
  USING (org_id = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK (org_id = current_setting('app.tenant_id', true)::uuid);
