"""PII Vault (ADR-0006).

Envelope encryption, done strictly:
- per-tenant DEK: random 32 bytes, wrapped with the master key. The wrap blob
  is ``nonce(12) || AESGCM(master, nonce, dek)`` so unwrapping is exact.
- field values: ``AESGCM(dek, fresh per-field nonce, value)``; nonce stored in
  ``pii.vault.iv``.
- ``decrypt`` requires a purpose from the allowed set and writes an audit row
  for every access. Plaintext exists only inside this boundary.

Business tables store vault ref ids and masked display values only.
"""
from __future__ import annotations

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from domain.intelligence.verification import mask_email

ALLOWED_PURPOSES = frozenset({"verification", "outreach", "human_review", "legal_request"})


def _wrap_dek(master: AESGCM, dek: bytes) -> bytes:
    nonce = os.urandom(12)
    return nonce + master.encrypt(nonce, dek, None)


def _unwrap_dek(master: AESGCM, blob: bytes) -> bytes:
    nonce, ct = bytes(blob[:12]), bytes(blob[12:])
    return master.decrypt(nonce, ct, None)


class PiiVault:
    """Tenant-agnostic engine; use TenantVault for the port surface."""

    def __init__(self, db, settings):
        self._db = db
        self._master = AESGCM(settings.master_key)

    def store(self, tenant_id: str, kind: str, value: str) -> str:
        assert kind in ("email", "phone"), "vault stores only email/phone"
        with self._db.tx(tenant_id) as conn, conn.cursor() as cur:
            row = cur.execute(
                "SELECT id, wrapped_dek FROM pii.deks WHERE org_id = %s ORDER BY created_at LIMIT 1",
                (tenant_id,),
            ).fetchone()
            if row:
                dek_id, dek = str(row["id"]), _unwrap_dek(self._master, bytes(row["wrapped_dek"]))
            else:
                dek = AESGCM.generate_key(bit_length=256)
                created = cur.execute(
                    "INSERT INTO pii.deks (org_id, wrapped_dek) VALUES (%s, %s) RETURNING id",
                    (tenant_id, _wrap_dek(self._master, dek)),
                ).fetchone()
                dek_id = str(created["id"])
            nonce = os.urandom(12)
            ciphertext = AESGCM(dek).encrypt(nonce, value.encode("utf-8"), None)
            ref = cur.execute(
                """INSERT INTO pii.vault (org_id, kind, ciphertext, iv, dek_id)
                   VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                (tenant_id, kind, ciphertext, nonce, dek_id),
            ).fetchone()
            return str(ref["id"])

    def decrypt(self, tenant_id: str, ref_id: str, purpose: str, actor: str,
                request_id: str | None = None) -> str:
        if purpose not in ALLOWED_PURPOSES:
            raise PermissionError(f"pii purpose {purpose!r} is not allowed")
        with self._db.tx(tenant_id) as conn, conn.cursor() as cur:
            row = cur.execute(
                """SELECT v.ciphertext, v.iv, d.wrapped_dek
                   FROM pii.vault v JOIN pii.deks d ON d.id = v.dek_id
                   WHERE v.org_id = %s AND v.id = %s""",
                (tenant_id, ref_id),
            ).fetchone()
            if row is None:
                raise KeyError(f"pii ref {ref_id} not found")
            dek = _unwrap_dek(self._master, bytes(row["wrapped_dek"]))
            value = AESGCM(dek).decrypt(bytes(row["iv"]), bytes(row["ciphertext"]), None)
            cur.execute(
                """INSERT INTO pii.pii_access_audit (org_id, ref_id, purpose, actor, request_id)
                   VALUES (%s, %s, %s, %s, %s)""",
                (tenant_id, ref_id, purpose, actor, request_id),
            )
            return value.decode("utf-8")

    def masked(self, kind: str, value: str) -> str:
        if kind == "email":
            local, _, domain = value.partition("@")
            return mask_email(local, domain)
        return value[:3] + "***" + value[-2:] if len(value) > 6 else "***"


class TenantVault:
    """The application port surface, bound to one tenant."""

    def __init__(self, engine: PiiVault, tenant_id: str):
        self._engine = engine
        self._tenant = tenant_id

    def store(self, kind: str, value: str) -> str:
        return self._engine.store(self._tenant, kind, value)

    def decrypt(self, ref_id: str, purpose: str, actor: str,
                request_id: str | None = None) -> str:
        return self._engine.decrypt(self._tenant, ref_id, purpose, actor, request_id)

    def masked(self, kind: str, value: str) -> str:
        return self._engine.masked(kind, value)
