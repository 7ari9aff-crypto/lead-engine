"""Forward-only SQL migration runner. The ONLY path for schema changes
(ADR-0001): no DDL at startup, no DDL during requests.

Two execution paths, chosen automatically:

1. Direct: the connecting role has DDL rights (local postgres).
2. Supabase Management API: the runtime role is DDL-restricted (Supabase's
   ``lead_engine`` role); SQL executes as ``postgres`` through the Management
   API. Requires LEAD_ENGINE_V6_SUPABASE_ACCESS_TOKEN + SUPABASE_PROJECT_REF.

Applied versions + checksums are tracked in runtime.schema_migrations; a
checksum mismatch aborts loudly instead of silently applying divergent SQL.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import psycopg

from .supabase_api import SupabaseSqlClient, apply_sql

TRACKING_SQL = """
CREATE SCHEMA IF NOT EXISTS runtime;
CREATE TABLE IF NOT EXISTS runtime.schema_migrations (
    version    text PRIMARY KEY,
    checksum   text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
);
"""


class MigrationConflict(RuntimeError):
    """A tracked migration file changed on disk."""


def _checksum(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def _supabase_client() -> SupabaseSqlClient | None:
    token = os.environ.get("LEAD_ENGINE_V6_SUPABASE_ACCESS_TOKEN", "").strip()
    ref = os.environ.get("SUPABASE_PROJECT_REF", "").strip()
    if not token or not ref:
        return None
    return SupabaseSqlClient(token, ref)


def _load_done(dsn: str) -> tuple[dict[str, str], SupabaseSqlClient | None]:
    """Return applied checksums + the API client when running via the API."""
    try:
        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute(TRACKING_SQL)
            rows = conn.execute(
                "SELECT version, checksum FROM runtime.schema_migrations"
            ).fetchall()
        return {r["version"]: r["checksum"] for r in rows}, None
    except psycopg.errors.InsufficientPrivilege:
        client = _supabase_client()
        if client is None:
            raise
        client.query(TRACKING_SQL)
        rows = client.query("SELECT version, checksum FROM runtime.schema_migrations")
        return {r["version"]: r["checksum"] for r in rows}, client


def apply_migrations(dsn: str, migrations_dir: Path, admin_dsn: str | None = None) -> list[str]:
    files = sorted(p for p in migrations_dir.glob("*.sql") if p.is_file())
    apply_dsn = admin_dsn or dsn
    done, api_client = _load_done(apply_dsn)
    applied: list[str] = []

    for path in files:
        version = path.stem
        sql = path.read_text(encoding="utf-8")
        checksum = _checksum(sql)
        if version in done:
            if done[version] != checksum:
                raise MigrationConflict(
                    f"{version} changed on disk after being applied "
                    f"({done[version][:12]} != {checksum[:12]})"
                )
            continue

        if api_client is not None:
            _apply_via_api(api_client, version, sql, checksum)
        else:
            _apply_direct(apply_dsn, version, sql, checksum)
        applied.append(version)
        print(f"  applied {version}")

    if api_client is not None:
        api_client.close()
    return applied


def _apply_direct(dsn: str, version: str, sql: str, checksum: str) -> None:
    with psycopg.connect(dsn) as conn:
        with conn.transaction():
            conn.execute(sql)
            conn.execute(
                "INSERT INTO runtime.schema_migrations (version, checksum) VALUES (%s, %s)",
                (version, checksum),
            )


def _apply_via_api(client: SupabaseSqlClient, version: str, sql: str, checksum: str) -> None:
    tracking = (
        "INSERT INTO runtime.schema_migrations (version, checksum)"
        f" VALUES ('{version}', '{checksum}');"
    )
    apply_sql(client, sql + "\n" + tracking)
