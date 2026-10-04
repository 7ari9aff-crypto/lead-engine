-- 20261004030000_vault_fingerprint.sql
-- Vault dedup, phase 1 (schema): every stored secret gets a keyed HMAC-
-- SHA256 fingerprint of its PLAINTEXT, computed by the application with the
-- deployment master key. Without the master key the fingerprint is not
-- invertible and not verifiable against guesses — it identifies repetition
-- ("the same email stored twice") without enabling recovery.
--
-- Uniqueness is per (org_id, kind, secret_fingerprint): the same value may
-- legitimately exist in different tenants or as email vs phone.
--
-- The UNIQUE index is created by scripts/backfill_vault_fingerprints.py
-- AFTER backfilling fingerprints and reconciling duplicates (re-point
-- contacts.contact_identities, then remove redundant rows) — creating it
-- first would break on existing duplicates.

ALTER TABLE pii.vault ADD COLUMN IF NOT EXISTS secret_fingerprint text;
CREATE INDEX IF NOT EXISTS idx_vault_fingerprint
  ON pii.vault (org_id, kind, secret_fingerprint);
