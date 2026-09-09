"""SQLite persistence: providers, usage ledger, jobs, leads, evidence, cache."""
import json
import sqlite3
from datetime import datetime, timezone


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
  notes TEXT,
  PRIMARY KEY (name, task)
);
CREATE TABLE IF NOT EXISTS usage_ledger (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  provider TEXT NOT NULL,
  task TEXT NOT NULL,
  job_id TEXT,
  units REAL DEFAULT 1,
  unit_kind TEXT,
  status TEXT,
  latency_ms INTEGER
);
CREATE TABLE IF NOT EXISTS jobs (
  job_id TEXT PRIMARY KEY,
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
"""


class Database:
    def __init__(self, path):
        self.conn = sqlite3.connect(str(path), timeout=10)
        self.conn.row_factory = sqlite3.Row
        # dashboard requests + background engine runs share the file:
        # WAL + busy_timeout keep concurrent readers/writers from clashing
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

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
        cols = ", ".join(row.keys())
        marks = ", ".join("?" for _ in row)
        self.execute(
            f"INSERT OR REPLACE INTO leads ({cols}) VALUES ({marks})",
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
