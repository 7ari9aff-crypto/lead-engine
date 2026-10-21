"""Org-scoped provider credentials for V6, without importing ``lead_engine``.

The operator's search/LLM keys live in ``public.organization_provider_credentials``
(AES-GCM, ``hex(iv || ciphertext)``, key = ``LEAD_ENGINE_ENCRYPTION_KEY``). The
legacy ``lead_engine.secrets.hydrate_environment`` read that table too, but it
swallowed every failure and returned a bare ``0`` (and each caller swallowed
again), so a worker with no keys looked identical to a healthy one. This module
reads the same table with the same format and reports *why* nothing was loaded.

Never logs or returns a secret value: only env-var NAMES and counts.
"""
from __future__ import annotations

import base64
import hashlib
import os
from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import dataclass, field

TABLE = "public.organization_provider_credentials"
_SELECT = (f"SELECT env_key, encrypted_value FROM {TABLE} "
           "WHERE organization_id = %s AND status = 'active'")


@dataclass(frozen=True)
class HydrationResult:
    org_id: str | None
    loaded: tuple[str, ...] = field(default_factory=tuple)   # env var names set from the store
    skipped_existing: tuple[str, ...] = field(default_factory=tuple)  # already set explicitly
    undecryptable: tuple[str, ...] = field(default_factory=tuple)     # bad rows (names only)
    reason: str | None = None   # why nothing was loaded; None when the read succeeded

    @property
    def org_fingerprint(self) -> str:
        """Non-secret, stable id for the org in logs. CI masks the raw org id as
        ``***`` (it is a repo secret), which made it impossible to tell WHICH
        org a worker hydrated from. First 8 hex of SHA-256: comparable, not
        reversible to the id."""
        if not self.org_id:
            return "none"
        return hashlib.sha256(self.org_id.encode()).hexdigest()[:8]

    @property
    def count(self) -> int:
        return len(self.loaded)

    def summary(self) -> str:
        if self.reason:
            return f"credential hydration (org#{self.org_fingerprint}): 0 keys, reason={self.reason}"
        parts = [f"loaded={len(self.loaded)} {list(self.loaded)}"]
        if self.skipped_existing:
            parts.append(f"kept_explicit_env={list(self.skipped_existing)}")
        if self.undecryptable:
            parts.append(f"undecryptable={list(self.undecryptable)}")
        return f"credential hydration (org#{self.org_fingerprint}): " + ", ".join(parts)


def _decrypt(blob: str, key: bytes) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    raw = bytes.fromhex(blob)
    return AESGCM(key).decrypt(raw[:12], raw[12:], None).decode()


def hydrate_environment(
    fetch_rows: Callable[[str], list[Mapping[str, str]]],
    org_id: str | None,
    *,
    environ: MutableMapping[str, str] | None = None,
) -> HydrationResult:
    """Load the org's active credentials into ``environ`` (default ``os.environ``).

    ``fetch_rows(org_id)`` returns ``[{env_key, encrypted_value}, ...]``. Explicit
    environment values are never overwritten. Never raises: every failure becomes
    a ``HydrationResult.reason`` so the caller can log the truth.
    """
    env = os.environ if environ is None else environ
    if not org_id:
        return HydrationResult(None, reason="LEAD_ENGINE_ORG_ID not set")
    raw_key = env.get("LEAD_ENGINE_ENCRYPTION_KEY", "")
    if not raw_key:
        return HydrationResult(org_id, reason="LEAD_ENGINE_ENCRYPTION_KEY not set")
    try:
        key = base64.urlsafe_b64decode(raw_key)
        if len(key) not in (16, 24, 32):
            return HydrationResult(org_id, reason="LEAD_ENGINE_ENCRYPTION_KEY has an invalid length")
    except Exception:
        return HydrationResult(org_id, reason="LEAD_ENGINE_ENCRYPTION_KEY is not valid base64")
    try:
        rows = fetch_rows(org_id)
    except Exception as exc:  # DB down, table missing, permissions...
        return HydrationResult(org_id, reason=f"credential store unreadable ({type(exc).__name__})")

    loaded: list[str] = []
    kept: list[str] = []
    bad: list[str] = []
    for row in rows:
        name = row["env_key"]
        try:
            value = _decrypt(row["encrypted_value"], key)
        except Exception:
            bad.append(name)      # a bad row must never break boot
            continue
        if not value:
            continue
        if name in env and env[name] and env[name] != value:
            kept.append(name)     # explicit env wins, exactly like the legacy loader
            continue
        if env.get(name) != value:
            env[name] = value
        loaded.append(name)
    return HydrationResult(org_id, tuple(loaded), tuple(kept), tuple(bad))


def hydrate_from_database(db, org_id: str | None) -> HydrationResult:
    """Production entry point: read through V6's own ``Database`` (system plane)."""
    def fetch(org: str):
        with db.tx_system() as conn, conn.cursor() as cur:
            cur.execute(_SELECT, (org,))
            return list(cur.fetchall())

    return hydrate_environment(fetch, org_id)


def hydrate_and_log(db, org_id: str | None, log=print) -> HydrationResult:
    """Boot helper shared by the API, the worker and the mounted app: hydrate and
    always say what happened. A missing key store is a warning, never a crash."""
    result = hydrate_from_database(db, org_id)
    log(("[credentials] " + result.summary()))
    return result
