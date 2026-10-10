-- 20261004040000_legal_policy_jurisdictions.sql
-- Port the four jurisdiction policies from public.policies into the
-- governance store as versioned DATA (the operator reviewed this content —
-- it is the same text that has lived in public.policies since Sep 9).
--
-- IMPORTANT — adoption is a separate, explicit act: these rows carry their
-- ORIGINAL published_at (Sep 9), so the baseline-v1 rows (published later,
-- with the code-default rule shape) remain the ACTIVE policy until the
-- operator publishes a translated jurisdiction row with a newer timestamp.
-- The raw jurisdiction shape (allowed_purposes/allowed_channels/…) is NOT
-- the evaluate() rule schema on purpose: translating it is the adoption
-- decision itself.
--
-- public.policies is a LEGACY Supabase table: on fresh v6-only databases
-- (CI service container) it does not exist and the port skips gracefully.

DO $$
BEGIN
  IF to_regclass('public.policies') IS NULL THEN
    RAISE NOTICE 'public.policies absent — jurisdiction port skipped';
    RETURN;
  END IF;

  INSERT INTO governance.legal_policy_versions (org_id, name, version, rules, published_at)
  SELECT o.target_org,
         'jurisdiction-' || p.jurisdiction,
         'raw-' || to_char(p.updated_at, 'YYYYMMDD'),
         jsonb_build_object(
           'jurisdiction', p.jurisdiction,
           'allowed_purposes', p.allowed_purposes,
           'allowed_channels', p.allowed_channels,
           'require_opt_out', p.require_opt_out,
           'notes', p.notes,
           'source', 'public.policies (raw — not yet in evaluate() schema)'),
         p.updated_at
  FROM public.policies p
  CROSS JOIN (SELECT DISTINCT o2.id AS target_org FROM platform.organizations o2) o
  WHERE NOT EXISTS (
    SELECT 1 FROM governance.legal_policy_versions v
    WHERE v.org_id = o.target_org AND v.name = 'jurisdiction-' || p.jurisdiction)
  ON CONFLICT (org_id, name, version) DO NOTHING;
END $$;
