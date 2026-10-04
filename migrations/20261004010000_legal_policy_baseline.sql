-- 20261004010000_legal_policy_baseline.sql
-- The governance gate is FAIL-CLOSED as of the accompanying code change: an
-- org with no adopted policy gets BLOCKED verdicts (recorded under the
-- 'fail-closed' version) instead of silently evaluating code defaults.
--
-- This migration ADOPTS the code's former defaults as versioned DATA for
-- every organization, so runtime behavior is preserved while decisions
-- become attributable to a real policy row. Stricter jurisdiction policies
-- (SA PDPL, AE, US, EU — currently in public.policies) are NOT ported here:
-- translating them into the evaluate() rule schema is a governance decision
-- that must be adopted explicitly (publish a newer version row per org).

INSERT INTO governance.legal_policy_versions (org_id, name, version, rules)
SELECT o.id, 'baseline', 'baseline-v1',
       '{"blocked_operations":["email.outbound_without_approval"],
         "review_operations":["email.outbound"],
         "blocked_countries":[],
         "require_country_allowlist":false,
         "country_allowlist":[],
         "suppressed_domains":["gov","edu","mil"]}'::jsonb
FROM platform.organizations o
WHERE NOT EXISTS (
  SELECT 1 FROM governance.legal_policy_versions v WHERE v.org_id = o.id)
ON CONFLICT (org_id, name, version) DO NOTHING;
