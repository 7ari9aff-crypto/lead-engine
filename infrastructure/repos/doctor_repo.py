"""SQL backend for the doctor sentinel."""
from __future__ import annotations

from pathlib import Path
from typing import Any


class DoctorRepo:
    def __init__(self, db, migrations_dir: Path):
        self.db = db
        self.migrations_dir = migrations_dir

    # -- raw surfaces ---------------------------------------------------------
    def system_one(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        with self.db.tx_system() as conn, conn.cursor() as cur:
            return cur.execute(sql, params).fetchone()

    def system_all(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        with self.db.tx_system() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())

    def org_all(self, org_id: str, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        with self.db.tx(org_id) as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())

    def org_exists(self, org_id: str) -> bool:
        # self-scoped: the org is visible to itself (FORCE RLS)
        with self.db.tx(org_id) as conn, conn.cursor() as cur:
            return cur.execute("SELECT 1 AS ok FROM platform.organizations WHERE id = %s",
                               (org_id,)).fetchone() is not None

    # -- migrations drift -------------------------------------------------------
    def applied_migrations(self) -> dict[str, str]:
        try:
            rows = self.system_all(
                "SELECT version, checksum FROM runtime.schema_migrations")
            return {r["version"]: r["checksum"] for r in rows}
        except Exception:  # noqa: BLE001 — drift IS the finding
            return {}

    def migration_files(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for path in sorted(self.migrations_dir.glob("*.sql")):
            out[path.stem] = __import__("hashlib").sha256(
                path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
        return out
