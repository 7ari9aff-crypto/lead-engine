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

DEV_MASTER_KEY_B64 = "3q2+7wIDh8aSb1mZnKpQvXyT5uJcR2eL4oP8gW0sA9E="  # dev-only; rotate in prod
DEV_SERVICE_TOKEN = "v6-dev-service-token"  # dev-only; service/CLI authentication

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


def _sanitize_dsn(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    kept = [(k, v) for k, v in query if k in _KEEP_PARAMS]
    if not any(k == "sslmode" for k, _ in kept):
        kept.append(("sslmode", "require"))
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(kept), "")
    )


@dataclass(frozen=True)
class Settings:
    database_url: str
    master_key: bytes
    service_token: str
    supabase_jwt_secret: str = ""
    redis_url: str = ""
    relay_batch_size: int = 100
    worker_poll_seconds: float = 1.0
    lease_seconds: int = 120
    extra: dict = field(default_factory=dict)

    @classmethod
    def load(cls) -> "Settings":
        _load_env_file(ENV_FILE)
        dsn = (
            os.environ.get("LEAD_ENGINE_V6_DATABASE_URL")
            or os.environ.get("SUPABASE_DB_URL")
            or "postgresql://ledev:ledev@localhost:5433/lead_engine_v6"
        )
        master_b64 = os.environ.get("LEAD_ENGINE_V6_MASTER_KEY", DEV_MASTER_KEY_B64)
        master_key = base64.b64decode(master_b64)
        if len(master_key) != 32:
            raise RuntimeError("LEAD_ENGINE_V6_MASTER_KEY must decode to 32 bytes")
        return cls(
            database_url=_sanitize_dsn(dsn),
            master_key=master_key,
            service_token=os.environ.get("V6_SERVICE_TOKEN", DEV_SERVICE_TOKEN),
            supabase_jwt_secret=os.environ.get("SUPABASE_JWT_SECRET", ""),
            redis_url=os.environ.get("LEAD_ENGINE_V6_REDIS_URL", ""),
        )
