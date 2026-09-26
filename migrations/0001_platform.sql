-- 0001: Platform context — tenancy, plans, entitlements, flags, usage.
-- RLS: organizations and usage_records are tenant-scoped. platform.members is
-- identity plane (resolve tenant FROM user), scoped by unique user_ext_id.

CREATE SCHEMA IF NOT EXISTS platform;

CREATE TABLE platform.plans (
  code        text PRIMARY KEY,
  limits      jsonb NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE platform.organizations (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug        text NOT NULL UNIQUE,
  name        text NOT NULL,
  plan_code   text NOT NULL REFERENCES platform.plans(code),
  region      text NOT NULL DEFAULT 'eu-west-1',
  placement   jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE platform.members (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id       uuid NOT NULL REFERENCES platform.organizations(id),
  user_ext_id  text NOT NULL,
  role         text NOT NULL CHECK (role IN ('owner','admin','member')),
  created_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (org_id, user_ext_id)
);
CREATE INDEX idx_platform_members_user ON platform.members (user_ext_id);

CREATE TABLE platform.feature_flags (
  key      text NOT NULL,
  org_id   uuid REFERENCES platform.organizations(id),
  enabled  boolean NOT NULL DEFAULT false,
  payload  jsonb NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY (key, org_id)
);

CREATE TABLE platform.usage_records (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL REFERENCES platform.organizations(id),
  kind        text NOT NULL,
  units       numeric NOT NULL DEFAULT 0,
  cost_cents  numeric NOT NULL DEFAULT 0,
  ref         jsonb,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_platform_usage_org ON platform.usage_records (org_id, created_at);

INSERT INTO platform.plans (code, limits) VALUES
  ('free', '{"max_concurrent_jobs":1,"max_provider_calls_per_day":200,"max_monthly_cost_cents":500}'),
  ('pro',  '{"max_concurrent_jobs":8,"max_provider_calls_per_day":20000,"max_monthly_cost_cents":50000}')
ON CONFLICT (code) DO NOTHING;

ALTER TABLE platform.organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE platform.organizations FORCE ROW LEVEL SECURITY;
CREATE POLICY organizations_tenant_isolation ON platform.organizations
  USING (id = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK (id = current_setting('app.tenant_id', true)::uuid);

ALTER TABLE platform.usage_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE platform.usage_records FORCE ROW LEVEL SECURITY;
CREATE POLICY usage_tenant_isolation ON platform.usage_records
  USING (org_id = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK (org_id = current_setting('app.tenant_id', true)::uuid);
