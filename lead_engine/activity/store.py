"""Platform-wide activity feed: event store over the engine Database interface.

The schema lives in this module instead of lead_engine/db.py so we don't touch
the core schema migrations. Both backends carry the same table: SQLite keeps it
in data/lead_engine.sqlite3, Postgres keeps it in the `engine` schema.
"""
import json
from datetime import datetime, timezone

_SCHEMA_SQLITE = """CREATE TABLE IF NOT EXISTS activity_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload_json TEXT,
    correlation_id TEXT
)"""

_SCHEMA_PG = """CREATE TABLE IF NOT EXISTS activity_events (
    id bigint generated always as identity primary key,
    ts timestamptz not null default now(),
    kind text not null,
    payload_json jsonb,
    correlation_id text
)"""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class ActivityStore:
    """Append-only event log. Kept intentionally small — no joins, no
    migrations beyond the table itself. The dashboard hits this every 5s."""

    def __init__(self, db):
        self.db = db
        self.db.execute(
            _SCHEMA_PG if getattr(db, "dialect", "sqlite") == "postgres"
            else _SCHEMA_SQLITE
        )

    def record(self, kind: str, payload: dict,
               correlation_id: str | None = None) -> dict:
        ts = _utcnow()
        payload_json = json.dumps(payload or {}, ensure_ascii=False, default=str)
        cur = self.db.execute(
            "INSERT INTO activity_events (ts, kind, payload_json, correlation_id)"
            " VALUES (?, ?, ?, ?)",
            (ts, kind, payload_json, correlation_id),
        )
        row_id = getattr(cur, "lastrowid", None)
        return self._row_to_dict({
            "id": row_id,
            "ts": ts,
            "kind": kind,
            "payload_json": payload_json,
            "correlation_id": correlation_id,
        })

    def list(self, limit: int = 50, kind: str | None = None) -> list[dict]:
        if limit < 1:
            limit = 1
        # Tenant scope: this org's events plus legacy platform rows (NULL).
        org_id = getattr(self.db, "org_id", None)
        where, params = [], []
        if org_id:
            where.append("(organization_id = ? OR organization_id IS NULL)")
            params.append(org_id)
        if kind:
            where.append("kind = ?")
            params.append(kind)
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        params.append(limit)
        rows = self.db.query(
            f"SELECT * FROM activity_events{clause} ORDER BY id DESC LIMIT ?",
            tuple(params),
        )
        return [self._row_to_dict(r) for r in rows]

    @staticmethod
    def _row_to_dict(row) -> dict:
        d = dict(row)
        raw = d.get("payload_json")
        if raw:
            try:
                d["payload"] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                d["payload"] = {}
        else:
            d["payload"] = {}
        # keep the raw string too so the row is fully reconstructable
        return d
