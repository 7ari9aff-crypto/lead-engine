"""Environment-driven configuration for the V6 stack.

Only infrastructure reads the environment (ADR-0003). Per the operator's
decision there is NO local Docker: development and tests run directly against
the Supabase Postgres, inside the dedicated V6 schemas (platform, acquisition,
company_identity, claims_evidence, contacts, intelligence, governance,
projects, pii, runtime, events, effects, agents). Legacy schemas
(public/engine/activity) are never touched.
"""
from __future__ import annotations

import base64
import os
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = REPO_ROOT / "migrations"
ENV_FILE = REPO_ROOT / ".env"



def _file_value(key: str) -> str:
    """Read one KEY from .env directly (bypassing blanked env overrides)."""
    if not ENV_FILE.exists():
        return ""
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(f"{key}="):
            return line.partition("=")[2].strip().strip('"').strip("'")
    return ""

def _dev_master_key() -> bytes:
    """Deterministic dev-only master key (NOT a stored secret): derived from a
    public label so no key material lives in source. Production MUST set
    LEAD_ENGINE_V6_MASTER_KEY; existing dev data encrypted under a different
    dev key stays decryptable only with that key in the environment."""
    import hashlib

    return hashlib.sha256(b"lead-engine-v6-dev-master-key").digest()
DEV_SERVICE_TOKEN = "v6-dev-service-token"  # dev-only; service/CLI authentication


def _is_production() -> bool:
    # LEAD_ENGINE_ENV is the explicit flag; VERCEL_ENV is set by Vercel itself
    # on every production deployment, so the guard holds even when the
    # operator never configured a flag.
    if (os.environ.get("LEAD_ENGINE_ENV") or "").strip().lower() == "production":
        return True
    return (os.environ.get("VERCEL_ENV") or "").strip().lower() == "production"

# Connection parameters libpq understands; anything else (pgbouncer=true,
# supa flags, ...) is dropped so psycopg never chokes on a Supabase DSN.
_KEEP_PARAMS = {"sslmode", "connect_timeout", "application_name", "target_session_attrs"}


def _load_env_file(path: Path) -> None:
    """Load KEY=VALUE pairs from .env into os.environ (no overwrite)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _nonblank_env(key: str) -> str:
    value = (os.environ.get(key) or "").strip()
    return value if value else ""


def _sanitize_dsn(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    kept = [(k, v) for k, v in query if k in _KEEP_PARAMS]
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(kept), "")
    )


@dataclass(frozen=True)
class Settings:
    database_url: str
    master_key: bytes
    service_token: str
    admin_database_url: str = ""
    public_base_url: str = ""
    supabase_jwt_secret: str = ""
    redis_url: str = ""
    relay_batch_size: int = 100
    worker_poll_seconds: float = 1.0
    lease_seconds: int = 120
    extra: dict = field(default_factory=dict)

    @classmethod
    def load(cls) -> "Settings":
        _load_env_file(ENV_FILE)
        # Priority: explicit V6 DSN > live env Supabase DSN > .env file value
        # (the file value saves us when a host blanks the env for legacy SQLite
        # mode but V6 still needs the authoritative Postgres).
        dsn = (
            os.environ.get("LEAD_ENGINE_V6_DATABASE_URL")
            or _nonblank_env("SUPABASE_DB_URL")
            or _file_value("SUPABASE_DB_URL")
            or os.environ.get("DATABASE_URL")
            or "postgresql://ledev:ledev@localhost:5433/lead_engine_v6"
        )
        master_b64 = os.environ.get("LEAD_ENGINE_V6_MASTER_KEY", "").strip()
        if master_b64:
            master_key = base64.b64decode(master_b64)
            if len(master_key) != 32:
                raise RuntimeError("LEAD_ENGINE_V6_MASTER_KEY must decode to 32 bytes")
        elif _is_production():
            # The dev key is derived from a public constant: silently using it
            # in production makes every PII vault value plaintext-equivalent.
            raise RuntimeError(
                "LEAD_ENGINE_V6_MASTER_KEY must be set in production "
                "(base64 of 32 bytes)")
        else:
            master_key = _dev_master_key()
        service_token = os.environ.get("V6_SERVICE_TOKEN", "").strip()
        if not service_token:
            if _is_production():
                # Fail-CLOSED without failing the boot: an unknown-to-everyone
                # token means service authentication is simply disabled this
                # boot. The old default (a public dev token) was an open door;
                # a boot crash would take the whole dashboard down instead.
                import secrets as _secrets
                import sys

                service_token = _secrets.token_urlsafe(32)
                print(
                    "[v6-config] WARNING: V6_SERVICE_TOKEN unset in production —"
                    " service authentication is DISABLED this boot (ephemeral"
                    " random token). Set V6_SERVICE_TOKEN to enable CLI/service"
                    " service access.",
                    file=sys.stderr)
            else:
                service_token = DEV_SERVICE_TOKEN
        return cls(
            database_url=_sanitize_dsn(dsn),
            master_key=master_key,
            admin_database_url=_sanitize_dsn(
                os.environ.get("LEAD_ENGINE_V6_ADMIN_DATABASE_URL") or dsn),
            # Empty means "unknown" — the doctor's http.surface check WARNs and
            # skips instead of probing a hardcoded deployment from dev/tests.
            public_base_url=(os.environ.get("LEAD_ENGINE_PUBLIC_BASE_URL") or "").strip(),
            service_token=service_token,
            supabase_jwt_secret=os.environ.get("SUPABASE_JWT_SECRET", ""),
            redis_url=os.environ.get("LEAD_ENGINE_V6_REDIS_URL", ""),
        )
