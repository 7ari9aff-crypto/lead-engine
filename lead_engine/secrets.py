"""Org-scoped provider credentials: AES-GCM encrypted at rest, hydrated into
the process environment on boot and after every save so the existing provider
adapters keep reading os.environ unchanged.

At-rest format: hex(iv || ciphertext). Key: LEAD_ENGINE_ENCRYPTION_KEY
(urlsafe base64, 32 bytes). No plaintext key material ever touches the DB.
"""
import base64
import os

_SECRET_TABLE = "organization_provider_credentials"


class SecretsUnavailable(RuntimeError):
    """Encryption key or org context missing — caller falls back to .env."""


def _key() -> bytes:
    raw = os.environ.get("LEAD_ENGINE_ENCRYPTION_KEY", "")
    if not raw:
        raise SecretsUnavailable("LEAD_ENGINE_ENCRYPTION_KEY not set")
    return base64.urlsafe_b64decode(raw)


def _aesgcm():
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    return AESGCM(_key())


def encrypt_secret(plain: str) -> str:
    import secrets as _secrets

    iv = _secrets.token_bytes(12)
    ct = _aesgcm().encrypt(iv, plain.encode(), None)
    return (iv + ct).hex()


def decrypt_secret(blob: str) -> str:
    raw = bytes.fromhex(blob)
    return _aesgcm().decrypt(raw[:12], raw[12:], None).decode()


def save_provider_credential(db, org_id: str, env_key: str, value: str) -> None:
    """Upsert one credential. Empty value deletes the row."""
    if not org_id or not os.environ.get("LEAD_ENGINE_ENCRYPTION_KEY"):
        raise SecretsUnavailable("org context or encryption key missing")
    if not value:
        db.execute(
            f"DELETE FROM public.{_SECRET_TABLE} WHERE organization_id = ? AND env_key = ?",
            (org_id, env_key))
        return
    existing = db.one(
        f"SELECT id FROM public.{_SECRET_TABLE} WHERE organization_id = ? AND env_key = ?",
        (org_id, env_key))
    encrypted = encrypt_secret(value)
    if existing:
        db.execute(
            f"UPDATE public.{_SECRET_TABLE} SET encrypted_value = ?, updated_at = now()"
            f" WHERE id = ?", (encrypted, existing["id"]))
    else:
        # env_key mirrors the provider's canonical env name
        db.execute(
            f"INSERT INTO public.{_SECRET_TABLE} (organization_id, provider_name, env_key,"
            f" encrypted_value) VALUES (?,?,?,?)",
            (org_id, env_key.replace("_API_KEY", "").replace("_KEY", "").lower(),
             env_key, encrypted))


def load_provider_credentials(db, org_id: str) -> dict[str, str]:
    """Decrypt all credentials for the org: {env_key: value}."""
    if not org_id or not os.environ.get("LEAD_ENGINE_ENCRYPTION_KEY"):
        return {}
    rows = db.query(
        f"SELECT env_key, encrypted_value FROM public.{_SECRET_TABLE}"
        f" WHERE organization_id = ? AND status = 'active'", (org_id,))
    out = {}
    for row in rows:
        try:
            out[row["env_key"]] = decrypt_secret(row["encrypted_value"])
        except Exception:
            continue  # a bad row must never break boot
    return out


def hydrate_environment(db, org_id: str | None) -> int:
    """Load org credentials into os.environ (no overwrite of explicit env).
    Returns how many keys were hydrated."""
    if not org_id:
        return 0
    try:
        creds = load_provider_credentials(db, org_id)
    except Exception:
        return 0
    count = 0
    for env_key, value in creds.items():
        if value and value != os.environ.get(env_key):
            os.environ[env_key] = value
            count += 1
    return count
