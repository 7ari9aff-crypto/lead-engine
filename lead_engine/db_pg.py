"""Postgres (Supabase) backend for the engine's operational store.

Selected automatically by db.open_db() when SUPABASE_DB_URL (or DATABASE_URL)
is set; SQLite stays the local dev/test backend with the same interface.

Adapter conventions — documented and covered by integration tests:
- Placeholders: callers write `?`; the adapter rewrites them to %s for
  psycopg. Engine SQL never contains a literal `?` inside statements.
- Timestamps: the engine passes ISO-8601 UTC strings (db.utcnow()); engine
  columns are timestamptz. Reads convert datetime values back to the exact
  engine format (%Y-%m-%dT%H:%M:%SZ) so existing string comparisons keep
  working unchanged.
- JSON columns (jsonb): the engine writes json.dumps() strings and reads
  with json.loads(); the adapter stringifies jsonb values on read.
- Numeric columns return Decimal from psycopg; converted to float to match
  SQLite arithmetic in the engine.
- organization_id: business tables (jobs, leads, usage_ledger, agent_runs,
  approvals) require it. The adapter injects the configured default org
  (org_id) when a caller omits it — Phase 1 single-org bridge; per-request
  tenant context replaces this in the auth layer.
"""
import decimal
import json
import re
from datetime import date, datetime, timezone

import psycopg
from psycopg.rows import dict_row

# Tables whose INSERTs must carry organization_id.
ORG_TABLES = {"jobs", "leads", "usage_ledger", "agent_runs", "approvals",
              "activity_events", "agents"}

_ORG_INSERT_RE = re.compile(
    r"(insert\s+into\s+(jobs|leads|usage_ledger|agent_runs|approvals|agents|activity_events)\s*)"
    r"\(([^)]*)\)\s*values\s*\(([^)]*)\)",
    re.IGNORECASE,
)

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _engine_ts(value: datetime) -> str:
    """Convert a DB datetime to the engine's canonical ISO string."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize(value):
    """Map PG-native types onto the shapes the engine expects."""
    if isinstance(value, datetime):
        return _engine_ts(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return value


def _translate_placeholders(sql: str) -> str:
    """Rewrite SQLite-style ? placeholders to psycopg %s."""
    return sql.replace("?", "%s")


def _inject_org(sql: str, params: list, org_id: str | None) -> tuple[str, list]:
    """Add organization_id to INSERTs on org-scoped tables when missing."""
    if not org_id:
        return sql, params

    def _add(match: re.Match) -> str:
        table = match.group(2)
        columns = match.group(3)
        values = match.group(4)
        if "organization_id" in columns.lower():
            return match.group(0)
        cols = f"{columns}, organization_id"
        vals = f"{values}, %s"
        params.append(org_id)
        return f"{match.group(1)}({cols}) VALUES ({vals})"

    return _ORG_INSERT_RE.sub(_add, sql), params


class _CursorProxy:
    """Exposes .lastrowid on psycopg cursors (which use __slots__)."""

    def __init__(self, cur, lastrowid=None):
        self._cur = cur
        self.lastrowid = lastrowid

    def __getattr__(self, name):
        return getattr(self._cur, name)


class PgDatabase:
    """Postgres implementation of the engine Database interface."""

    dialect = "postgres"

    # Tables with identity columns — INSERTs into them expose lastrowid.
    _IDENTITY_TABLES = (
        "agent_steps", "activity_events", "evidence",
        "usage_ledger", "job_events", "audit_logs",
    )

    def __init__(self, dsn: str, org_id: str | None = None):
        self.org_id = org_id
        # Engine SQL uses unqualified table names (jobs, leads, ...) — they
        # MUST resolve to the `engine` schema, never to public.* (which holds
        # the legacy sync tables with different columns). Transaction-pooler
        # compatibility: prepared statements disabled.
        self.conn = psycopg.connect(
            dsn, row_factory=dict_row, autocommit=False,
            options="-c search_path=engine", prepare_threshold=None,
        )

    # -- low level ------------------------------------------------------
    def execute(self, sql: str, params=()):
        sql = _translate_placeholders(sql)
        params = list(params or [])
        if re.search(r"insert\s+into", sql, re.IGNORECASE):
            sql, params = _inject_org(sql, params, self.org_id)
        cur = self.conn.cursor()
        cur.execute(sql, params)
        self.conn.commit()
        # Identity tables expose lastrowid (agent_steps.start_step,
        # activity_events.record, ...) via lastval.
        lowered = sql.lower()
        if lowered.lstrip().startswith("insert into") and any(
            f"insert into {t}" in lowered for t in self._IDENTITY_TABLES
        ):
            cur.execute("SELECT lastval() AS id")
            row = cur.fetchone()
            return _CursorProxy(cur, row["id"] if row else None)
        return _CursorProxy(cur)

    def query(self, sql: str, params=()) -> list[dict]:
        cur = self.conn.cursor()
        cur.execute(_translate_placeholders(sql), list(params or []))
        rows = cur.fetchall()
        self.conn.commit()
        return [{k: _normalize(v) for k, v in row.items()} for row in rows]

    def one(self, sql: str, params=()) -> dict | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    # -- leads ----------------------------------------------------------
    LEAD_COLUMNS = (
        "lead_id", "job_id", "name", "domain", "city", "country", "industry",
        "employee_count", "branches", "phone", "email", "email_status",
        "email_confidence", "decision_maker", "decision_maker_title", "linkedin",
        "website", "social", "qualification_score", "tier", "score", "stage",
        "processing_mode", "requires_review", "legal_decision", "data_types",
        "sources", "source_queries", "raw", "created_at", "updated_at",
    )

    def insert_lead(self, lead: dict) -> None:
        lead["lead_id"] = lead.get("lead_id") or (
            f"{lead.get('job_id', 'job')}:{lead.get('domain') or lead.get('name')}")
        from .db import utcnow

        now = utcnow()
        lead.setdefault("created_at", now)
        lead["updated_at"] = now
        extra = {k: v for k, v in lead.items() if k not in self.LEAD_COLUMNS}
        if extra:
            stored_raw = lead.get("raw")
            if isinstance(stored_raw, str):
                try:
                    stored_raw = json.loads(stored_raw)
                except (json.JSONDecodeError, TypeError):
                    stored_raw = {"stored_raw": stored_raw}
            lead["raw"] = json.dumps(
                {"stored_raw": stored_raw or {}, "pipeline": extra},
                ensure_ascii=False, default=str)
        row = {k: lead.get(k) for k in self.LEAD_COLUMNS}
        for key in ("sources", "source_queries", "data_types"):
            if isinstance(row[key], (list, tuple)):
                row[key] = json.dumps(row[key], ensure_ascii=False)
        if row["requires_review"] is True:
            row["requires_review"] = 1
        cols = list(row.keys())
        updates = ", ".join(
            f"{c} = excluded.{c}" for c in cols if c != "lead_id")
        sql = (
            f"INSERT INTO leads ({', '.join(cols)}) "
            f"VALUES ({', '.join('?' for _ in cols)}) "
            f"ON CONFLICT (lead_id) DO UPDATE SET {updates}"
        )
        self.execute(sql, list(row.values()))

    def leads_for_job(self, job_id: str):
        return self.query("SELECT * FROM leads WHERE job_id = ?", (job_id,))

    def add_evidence(self, lead_id, claim, source, method, expires_at=None):
        self.execute(
            "INSERT INTO evidence (lead_id, claim, source, collection_method,"
            " collected_at, expires_at) VALUES (?,?,?,?,?,?)",
            (lead_id, claim, source, method, _engine_ts(datetime.now(timezone.utc)),
             expires_at),
        )

    def evidence_for(self, lead_id):
        return self.query("SELECT * FROM evidence WHERE lead_id = ?", (lead_id,))

    # -- misc -----------------------------------------------------------
    def close(self):
        self.conn.close()
