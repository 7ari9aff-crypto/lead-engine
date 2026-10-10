-- 20261004050000_webhook_endpoints.sql
-- Outbound webhook registry for the v6 event plane (the integration layer
-- competitors ship as "CRM integrations"). Events published on events.outbox
-- (LEAD_READY_FOR_REVIEW / LEAD_APPROVED / …) are delivered HMAC-signed to
-- every enabled endpoint of the event's org by the webhook consumer.
--
-- The signing secret is stored AES-GCM encrypted (hex(iv||ct)) under the
-- deployment master key — the same envelope discipline as the PII vault.

CREATE TABLE IF NOT EXISTS events.webhook_endpoints (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL REFERENCES platform.organizations(id),
  url         text NOT NULL,
  secret_enc  text NOT NULL,
  events      text[] NOT NULL DEFAULT '{*}',
  enabled     boolean NOT NULL DEFAULT true,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_webhook_endpoints_org
  ON events.webhook_endpoints (org_id) WHERE enabled;

ALTER TABLE events.webhook_endpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE events.webhook_endpoints FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON events.webhook_endpoints
  USING (org_id = public.app_tenant_uuid())
  WITH CHECK (org_id = public.app_tenant_uuid());
