# ADR-0006 — PII vault: envelope encryption with purpose-bound access

Status: accepted (implements locked invariants)

- Contact emails/phones never live as plaintext in business tables. Contacts
  and lead projections store `pii_ref` ids and masked display values.
- `pii.vault` stores AES-256-GCM ciphertext (per-field IV). Data is encrypted
  with a per-tenant DEK; each DEK is wrapped with the master key
  (`LEAD_ENGINE_V6_MASTER_KEY`, base64 32 bytes). In production the master key
  moves to a KMS — the vault interface is KMS-shaped already.
- Decryption requires `decrypt(org_id, ref, purpose, actor)` with purpose in
  {verification, outreach, human_review, legal_request}; every access is
  written to `pii.pii_access_audit`.
- PII is forbidden in logs, events, analytics, cache, agent memory, prompts
  and traces. Agents only ever see contact ids + masked values.
