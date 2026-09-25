"""Platform-wide activity feed: event store over the engine Database interface.

The schema lives in this module instead of lead_engine/db.py so we don't touch
the core schema migrations. Both backends carry the same table: SQLite keeps it
in data/lead_engine.sqlite3, Postgres keeps it in the `engine` schema.

`AuditTrailStore` (bottom of this file) is the READ path over `audit_logs`,
the server-side provenance table written by db.audit()/PgDatabase.audit()/
codeops.audit(). Until now that table was write-only.
"""
import json
from datetime import datetime, timedelta, timezone

_SCHEMA_SQLITE = """CREATE TABLE IF NOT EXISTS activity_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id TEXT,
    ts TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload_json TEXT,
    correlation_id TEXT
)"""

_SCHEMA_PG = """CREATE TABLE IF NOT EXISTS activity_events (
    id bigint generated always as identity primary key,
    organization_id text,
    ts timestamptz not null default now(),
    kind text not null,
    payload_json jsonb,
    correlation_id text
)"""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_schema(db) -> None:
    """Create the activity table. Called from startup and `init`, never per request.

    On Postgres this is expected to fail with `permission denied for schema engine`
    because migrations own DDL there; the startup hook logs it and moves on.
    """
    postgres = getattr(db, "dialect", "sqlite") == "postgres"
    db.execute(_SCHEMA_PG if postgres else _SCHEMA_SQLITE)
    if postgres:
        db.execute(
            "ALTER TABLE activity_events ADD COLUMN IF NOT EXISTS organization_id TEXT"
        )
        return
    # Add tenant scope to pre-existing activity tables without data loss.
    existing = {row["name"] for row in db.conn.execute(
        "PRAGMA table_info(activity_events)"
    )}
    if "organization_id" not in existing:
        db.execute("ALTER TABLE activity_events ADD COLUMN organization_id TEXT")


class ActivityStore:
    """Append-only event log. Kept intentionally small — no joins, no migrations
    beyond the table itself, and no schema work on the request path. The
    dashboard hits this every 5s."""

    def __init__(self, db):
        self.db = db

    def record(self, kind: str, payload: dict,
               correlation_id: str | None = None) -> dict:
        ts = _utcnow()
        payload_json = json.dumps(payload or {}, ensure_ascii=False, default=str)
        organization_id = getattr(self.db, "org_id", None)
        cur = self.db.execute(
            "INSERT INTO activity_events"
            " (organization_id, ts, kind, payload_json, correlation_id)"
            " VALUES (?, ?, ?, ?, ?)",
            (organization_id, ts, kind, payload_json, correlation_id),
        )
        row_id = getattr(cur, "lastrowid", None)
        return self._row_to_dict({
            "id": row_id,
            "organization_id": organization_id,
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


# ---------------------------------------------------------------------------
# audit_logs read path (server-side provenance)
# ---------------------------------------------------------------------------

_NO_ORG_SENTINEL = "__no_org__"

# Columns we read; explicit so a schema drift fails loudly, not silently.
_AUDIT_COLUMNS = ("id, organization_id, actor, action, entity_type, entity_id,"
                  " payload_json, created_at")


def _canonical_ts(value) -> str | None:
    """Normalise a stored created_at to the engine's canonical ISO-8601 UTC
    string (%Y-%m-%dT%H:%M:%SZ). SQLite stores the writer's raw text (db.utcnow
    form, or codeops' isoformat with +00:00 / microseconds); the Postgres
    adapter already normalises timestamptz on read. Parsing here makes both
    dialects return byte-identical timestamps to the client."""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).strip())
        except ValueError:
            return str(value)  # unparseable: surface it unchanged
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _window_bound(value, *, end: bool = False) -> str | None:
    """Validate/normalise a caller-supplied time-window bound to the canonical
    UTC form. Accepts 'YYYY-MM-DD' (expanded: start-of-day, or end-of-day for
    `until` so the named day is inclusive) and full ISO-8601 (naive = UTC).
    Raises ValueError on garbage so the API layer can answer 400.

    Dialect semantics: on Postgres the timestamptz column parses the bound, so
    window edges are exact. On SQLite created_at is TEXT and the comparison is
    lexicographic — correct for the canonical 'Z' form the engine's own writer
    (db.utcnow) produces, with one documented wrinkle: codeops rows carry
    '+00:00'/microseconds, so a bound landing on the same second as such a row
    is inclusive at the upper edge and exclusive at the lower edge. The audit
    reader's windows are day/month boundaries; the 1s corner is not worth a
    non-sargable substr() comparison on both dialects.
    """
    if value is None or not str(value).strip():
        return None
    s = str(value).strip()
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00").replace("z", "+00:00"))
    except ValueError:
        raise ValueError(
            f"invalid timestamp {value!r}: use ISO-8601, e.g. 2026-09-25 "
            "or 2026-09-25T13:30:00Z") from None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if end and len(s) == 10:  # date-only `until`: include the whole day
        dt = dt + timedelta(days=1) - timedelta(seconds=1)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class AuditTrailStore:
    """Single-statement, tenant-scoped reads over `audit_logs`.

    Discipline (gap register LAT-01, same as ActivityStore): the constructor
    issues zero statements — no ensure_schema on the request path. Each `list()`
    call costs exactly ONE SELECT regardless of page size or row count; payload
    JSON and timestamps are parsed in Python, never with json()/->> in SQL, so
    the same query works on SQLite (payload_json TEXT, created_at TEXT) and on
    Postgres (jsonb / timestamptz — the db_pg adapter stringifies both on read).

    Tenant visibility — deliberate, stricter than ActivityStore's
    "(own org OR NULL) legacy rows" rule. audit payloads can name another
    tenant's entity ids, so cross-tenant leakage of even unattributed rows is
    a compliance bug here in a way it is not for the activity ticker:
      * real org            -> ONLY rows with organization_id = that org.
      * '__no_org__'-style  -> NOTHING (fail closed, zero statements): a user
        whose membership could not resolve has no business reading provenance.
      * no org (worker/n8n/ -> ONLY rows NOT attributable to any tenant:
        machine contexts      organization_id NULL or '' or the '__no_org__'
        sentinel — platform operators are the only audience for a fail-closed
        user's actions; no tenant ever sees them.
    tenant.org_clause() is NOT reused: it returns an empty predicate when the
    org is absent, which would expose every tenant's rows to a context-less
    caller. Fine under forced RLS for business tables, unacceptable here —
    audit_logs has no RLS (the write path must never fail), so the WHERE is
    the only isolation that exists.
    """

    def __init__(self, db):
        self.db = db

    def _scope(self) -> tuple[str, list, str]:
        """(SQL fragment incl. leading WHERE, params, scope name)."""
        org = getattr(self.db, "org_id", None)
        org = str(org).strip() if org is not None else ""
        if org.startswith("__") and org != "":
            # '__no_org__' and friends: fail closed. Caller-name is hidden so
            # the sentinel stays one opaque concept for the frontend.
            return "WHERE 1 = 0", [], "none"
        if org:
            return "WHERE organization_id = ?", [org], "tenant"
        return ("WHERE (organization_id IS NULL OR organization_id = ?"
                " OR organization_id = ?)", ["", _NO_ORG_SENTINEL], "platform")

    def list(self, *, limit: int = 50, offset: int = 0,
             actor: str | None = None, action: str | None = None,
             entity_type: str | None = None, entity_id: str | None = None,
             created_from: str | None = None, created_to: str | None = None,
             before_id: int | None = None) -> dict:
        """Newest-first page of audit entries. Returns the rows plus the scope
        label; `before_id` is the keyset cursor (ORDER BY id DESC — created_at
        is second-precision so it ties; id is monotonic and stable across
        pages). One SELECT; the sentinel/none scope short-circuits to zero."""
        where, params, scope = self._scope()
        if before_id is not None:
            where += " AND id < ?"
            params.append(int(before_id))
        for column, value in (("actor", actor), ("action", action),
                              ("entity_type", entity_type), ("entity_id", entity_id)):
            if value:
                where += f" AND {column} = ?"
                params.append(value)
        lower = _window_bound(created_from)
        if lower:
            where += " AND created_at >= ?"
            params.append(lower)
        upper = _window_bound(created_to, end=True)
        if upper:
            where += " AND created_at <= ?"
            params.append(upper)
        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset))
        if scope == "none":
            return {"entries": [], "scope": scope}
        rows = self.db.query(
            f"SELECT {_AUDIT_COLUMNS} FROM audit_logs {where}"
            " ORDER BY id DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        )
        return {"entries": [self._row_to_dict(r) for r in rows], "scope": scope}

    @staticmethod
    def _row_to_dict(row) -> dict:
        d = dict(row)
        raw = d.get("payload_json")
        if isinstance(raw, (dict, list)):  # defensive: unmapped jsonb
            d["payload"] = raw
        elif raw:
            try:
                d["payload"] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                d["payload"] = {}
        else:
            d["payload"] = {}
        d["created_at"] = _canonical_ts(d.get("created_at"))
        return d
