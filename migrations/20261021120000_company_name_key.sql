-- Language-aware matching key for company names (Arabic spelling variants,
-- tashkeel, ال prefix, honorifics, generic business words). canonical_name stays
-- the human-readable display value; name_key is only for matching.
--
-- ADDITIVE ONLY: one nullable column + one index. Nothing is deleted, merged or
-- rewritten. Rows created before this migration keep name_key NULL until the
-- idempotent backfill (scripts/backfill_company_name_key.py) fills them, and
-- the repo falls back to the old canonical_name match for those rows.

ALTER TABLE company_identity.companies
  ADD COLUMN IF NOT EXISTS name_key text;

CREATE INDEX IF NOT EXISTS idx_company_name_key
  ON company_identity.companies (org_id, name_key)
  WHERE name_key IS NOT NULL AND merged_into_id IS NULL;
