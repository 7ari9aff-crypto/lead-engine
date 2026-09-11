"""Platform-wide activity feed: SQLite-backed event store.

The activity feed is the unified timeline of platform events (job runs,
agent runs, approvals, provider events). The schema lives in this module
instead of lead_engine/db.py so we don't touch the core schema migrations.
"""
import json
from datetime import datetime, timezone

_SCHEMA = """CREATE TABLE IF NOT EXISTS activity_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload_json TEXT,
    correlation_id TEXT
)"""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class ActivityStore:
    """Append-only event log. Kept intentionally small — no joins, no
    migrations beyond the table itself. The dashboard hits this every 5s."""

    def __init__(self, db):
        self.db = db
        self.db.conn.executescript(_SCHEMA)
        self.db.conn.commit()

    def record(self, kind: str, payload: dict,
               correlation_id: str | None = None) -> dict:
        ts = _utcnow()
        payload_json = json.dumps(payload or {}, ensure_ascii=False, default=str)
        cur = self.db.conn.execute(
            "INSERT INTO activity_events (ts, kind, payload_json, correlation_id)"
            " VALUES (?, ?, ?, ?)",
            (ts, kind, payload_json, correlation_id),
        )
        self.db.conn.commit()
        row_id = cur.lastrowid
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
        if kind:
            rows = self.db.conn.execute(
                "SELECT * FROM activity_events WHERE kind = ?"
                " ORDER BY id DESC LIMIT ?",
                (kind, limit),
            ).fetchall()
        else:
            rows = self.db.conn.execute(
                "SELECT * FROM activity_events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
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
