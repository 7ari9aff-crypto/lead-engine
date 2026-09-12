"""SQLite + Postgres persistence: providers, usage ledger, jobs, leads, evidence, cache.

open_db() picks the backend: Postgres (Supabase) when SUPABASE_DB_URL /
DATABASE_URL is set — the production path — else the local SQLite store
used for dev and tests. Both implement the same Database interface.
"""
import json
import os
import sqlite3
from datetime import datetime, timezone

from .config import DB_PATH  # single source of truth for the SQLite path


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def open_db(org_id: str | None = None):
    """Backend factory. Production: Supabase Postgres. Dev/tests: SQLite.

    org_id wins over the LEAD_ENGINE_ORG_ID env bridge so request-scoped
    handlers can pin the tenant explicitly."""
    dsn = os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL")
    if dsn:
        from .db_pg import PgDatabase

        return PgDatabase(dsn, org_id=org_id or os.environ.get("LEAD_ENGINE_ORG_ID"))
    return Database(DB_PATH)


SCHEMA = """
CREATE TABLE IF NOT EXISTS providers (
  name TEXT NOT NULL,
  task TEXT NOT NULL,
  type TEXT,
  priority INTEGER DEFAULT 99,
  quota_kind TEXT,          -- credits | usd | requests | account | dynamic | unlimited
  quota_limit REAL,
  quota_used REAL DEFAULT 0,
  period TEXT,              -- monthly | none
  period_start TEXT,
  rpm_limit INTEGER,
  status TEXT DEFAULT 'active',
  status_reason TEXT,
  cooldown_until TEXT,
  env_key TEXT,
    base_url TEXT,
    model_name TEXT,
  notes TEXT,
  PRIMARY KEY (name, task)
);
CREATE TABLE IF NOT EXISTS usage_ledger (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  organization_id TEXT,
  ts TEXT NOT NULL,
  provider TEXT NOT NULL,
  task TEXT NOT NULL,
  job_id TEXT,
  units REAL DEFAULT 1,
  unit_kind TEXT,
  status TEXT,
  latency_ms INTEGER,
  prompt_tokens INTEGER DEFAULT 0,
  completion_tokens INTEGER DEFAULT 0,
  key_index INTEGER
);
CREATE TABLE IF NOT EXISTS jobs (
  job_id TEXT PRIMARY KEY,
  organization_id TEXT,
  icp_id TEXT,
  state TEXT NOT NULL,
  pause_reason TEXT,
  resume_at TEXT,
  params TEXT,
  result TEXT,
  created_at TEXT,
  updated_at TEXT
);
CREATE TABLE IF NOT EXISTS job_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  job_id TEXT NOT NULL,
  from_state TEXT,
  to_state TEXT,
  reason TEXT
);
CREATE TABLE IF NOT EXISTS leads (
  lead_id TEXT PRIMARY KEY,
  organization_id TEXT,
  job_id TEXT,
  name TEXT,
  domain TEXT,
  city TEXT,
  country TEXT,
  industry TEXT,
  employee_count INTEGER,
  branches INTEGER,
  phone TEXT,
  email TEXT,
  email_status TEXT,
  email_confidence REAL,
  decision_maker TEXT,
  decision_maker_title TEXT,
  linkedin TEXT,
  website TEXT,
  social TEXT,
  qualification_score REAL,
  tier TEXT,
  score REAL,
  stage TEXT,               -- ACCEPTED | REVIEW | REJECTED
  processing_mode TEXT,     -- cloud | degraded_local
  requires_review INTEGER DEFAULT 0,
  legal_decision TEXT,
  data_types TEXT,
  sources TEXT,
  source_queries TEXT,
  raw TEXT,
  created_at TEXT,
  updated_at TEXT
);
CREATE TABLE IF NOT EXISTS evidence (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lead_id TEXT NOT NULL,
  claim TEXT NOT NULL,
  source TEXT,
  collection_method TEXT,
  collected_at TEXT,
  expires_at TEXT
);
CREATE TABLE IF NOT EXISTS cache (
  level INTEGER NOT NULL,
  cache_key TEXT NOT NULL,
  payload TEXT,
  data_type TEXT,
  created_at TEXT,
  expires_at TEXT,
  PRIMARY KEY (level, cache_key)
);
CREATE TABLE IF NOT EXISTS agents (
    agent_id TEXT PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    current_version TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS agent_versions (
    agent_id TEXT NOT NULL,
    version TEXT NOT NULL,
    instructions TEXT,
    model_policy TEXT,
    model_provider TEXT,         -- gemini | groq | openrouter | ollama | router
    model_name TEXT,             -- optional explicit model id (e.g. gemini-2.5-pro)
    thinking_effort TEXT,        -- low | medium | high | max (model-specific support)
    tool_policy TEXT,
    output_schema TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT,
    PRIMARY KEY (agent_id, version)
);
CREATE TABLE IF NOT EXISTS agent_runs (
    run_id TEXT PRIMARY KEY,
    organization_id TEXT,
    agent_id TEXT NOT NULL,
    version TEXT NOT NULL,
    status TEXT NOT NULL,
    input_json TEXT,
    output_json TEXT,
    error TEXT,
    cost_usd REAL DEFAULT 0,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS agent_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    step_name TEXT NOT NULL,
    step_type TEXT,
    status TEXT NOT NULL,
    input_json TEXT,
    output_json TEXT,
    provider TEXT,
    latency_ms INTEGER,
    error TEXT,
    started_at TEXT,
    finished_at TEXT
);
CREATE TABLE IF NOT EXISTS tools (
    name TEXT PRIMARY KEY,
    description TEXT,
    input_schema TEXT,
    output_schema TEXT,
    scopes TEXT,
    requires_approval INTEGER DEFAULT 0,
    enabled INTEGER DEFAULT 1,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS connections (
    connection_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    kind TEXT NOT NULL,
    base_url TEXT,
    status TEXT NOT NULL DEFAULT 'unknown',
    last_checked_at TEXT,
    metadata_json TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT PRIMARY KEY,
    organization_id TEXT,
    run_id TEXT NOT NULL,
    step_id INTEGER,
    action TEXT NOT NULL,
    payload_json TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING',
    requested_at TEXT,
    resolved_at TEXT
);
"""


class Database:

    dialect = "sqlite"

    def __init__(self, path):
        # check_same_thread=False: FastAPI sync dependencies run in a worker
        # thread while async endpoints run in the loop thread; connections are
        # short-lived per request and WAL + busy_timeout handle the rest.
        self.conn = sqlite3.connect(str(path), timeout=10, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        # dashboard requests + background engine runs share the file:
        # WAL + busy_timeout keep concurrent readers/writers from clashing
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.executescript(SCHEMA)
        self._migrate_provider_columns()
        self._migrate_usage_columns()
        self._migrate_agent_version_columns()
        self.conn.commit()

    def _migrate_provider_columns(self):
        existing = {row["name"] for row in self.conn.execute("PRAGMA table_info(providers)")}
        for name, definition in (("base_url", "TEXT"), ("model_name", "TEXT")):
            if name not in existing:
                self.conn.execute(f"ALTER TABLE providers ADD COLUMN {name} {definition}")

    def _migrate_usage_columns(self):
        existing = {row["name"] for row in self.conn.execute("PRAGMA table_info(usage_ledger)")}
        for name, definition in (
            ("prompt_tokens", "INTEGER DEFAULT 0"),
            ("completion_tokens", "INTEGER DEFAULT 0"),
            ("key_index", "INTEGER"),
        ):
            if name not in existing:
                self.conn.execute(f"ALTER TABLE usage_ledger ADD COLUMN {name} {definition}")

    def _migrate_agent_version_columns(self):
        existing = {row["name"] for row in self.conn.execute("PRAGMA table_info(agent_versions)")}
        for name, definition in (
            ("model_provider", "TEXT"),
            ("model_name", "TEXT"),
            ("thinking_effort", "TEXT"),
        ):
            if name not in existing:
                self.conn.execute(f"ALTER TABLE agent_versions ADD COLUMN {name} {definition}")
        # Backfill: existing version rows from older schemas had no model_provider.
        # Treat them as "router" (the legacy default) so the chat layer doesn't break.
        self.conn.execute(
            "UPDATE agent_versions SET model_provider='router'"
            " WHERE model_provider IS NULL OR model_provider=''"
        )

    def execute(self, sql, params=()):
        cur = self.conn.execute(sql, params)
        self.conn.commit()
        return cur

    def query(self, sql, params=()):
        return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def one(self, sql, params=()):
        row = self.conn.execute(sql, params).fetchone()
        return dict(row) if row else None

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
            f"{lead.get('job_id','job')}:{lead.get('domain') or lead.get('name')}")
        now = utcnow()
        lead.setdefault("created_at", now)
        lead["updated_at"] = now
        extra = {k: v for k, v in lead.items() if k not in self.LEAD_COLUMNS}
        if extra:
            lead["raw"] = json.dumps(
                {"stored_raw": json.loads(lead["raw"]) if isinstance(lead.get("raw"), str)
                 else (lead.get("raw") or {}), "pipeline": extra},
                ensure_ascii=False, default=str)
        row = {k: lead.get(k) for k in self.LEAD_COLUMNS}
        for key in ("sources", "source_queries", "data_types"):
            if isinstance(row[key], (list, tuple)):
                row[key] = json.dumps(row[key], ensure_ascii=False)
        if row["requires_review"] is True:
            row["requires_review"] = 1
        cols = list(row.keys())
        updates = ", ".join(f"{c} = excluded.{c}" for c in cols if c != "lead_id")
        self.execute(
            f"INSERT INTO leads ({', '.join(cols)}) "
            f"VALUES ({', '.join('?' for _ in cols)}) "
            f"ON CONFLICT (lead_id) DO UPDATE SET {updates}",
            list(row.values()),
        )

    def leads_for_job(self, job_id: str):
        return self.query("SELECT * FROM leads WHERE job_id = ?", (job_id,))

    def add_evidence(self, lead_id, claim, source, method, expires_at=None):
        self.execute(
            "INSERT INTO evidence (lead_id, claim, source, collection_method, collected_at, expires_at)"
            " VALUES (?,?,?,?,?,?)",
            (lead_id, claim, source, method, utcnow(), expires_at),
        )

    def evidence_for(self, lead_id):
        return self.query("SELECT * FROM evidence WHERE lead_id = ?", (lead_id,))
