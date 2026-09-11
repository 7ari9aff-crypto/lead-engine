"""Provider Registry — database table, not if/else in code.

Tracks per (provider, task): priority, quota, usage, rate limits, status.
The router reads from here and updates it from real responses
(Retry-After / x-ratelimit headers), so decisions are data-driven.
"""
from datetime import datetime, timedelta, timezone

from .config import load_env
from .db import utcnow

# (name, type, task, priority, quota_kind, quota_limit, period, rpm, env_key)
# quotas per provider marketing pages as of design time — verify in V0.
SEED = [
    ("tavily",      "search", "web_search",   1, "credits",   1000, "monthly", None, "TAVILY_API_KEY"),
    ("brave",       "search", "web_search",   2, "usd",       5.0,  "monthly", None, "BRAVE_SEARCH_API_KEY"),
    ("exa",         "search", "web_search",   3, "usd",       10.0, "monthly", None, "EXA_API_KEY"),
    ("gemini",      "llm",    "reasoning",    1, "dynamic",   None, "none",    None, "GEMINI_API_KEY"),
    ("groq",        "llm",    "reasoning",    2, "dynamic",   None, "none",    None, "GROQ_API_KEY"),
    ("openrouter",  "llm",    "reasoning",    3, "dynamic",   None, "none",    None, "OPENROUTER_API_KEY"),
    ("ollama",      "llm",    "reasoning",    4, "unlimited", None, "none",    None, None),
    ("groq",        "llm",    "inference",    1, "dynamic",   None, "none",    None, "GROQ_API_KEY"),
    ("gemini",      "llm",    "inference",    2, "dynamic",   None, "none",    None, "GEMINI_API_KEY"),
    ("openrouter",  "llm",    "inference",    3, "dynamic",   None, "none",    None, "OPENROUTER_API_KEY"),
    ("ollama",      "llm",    "inference",    4, "unlimited", None, "none",    None, None),
    ("apollo",      "data",   "people_search",1, "requests",  None, "none",    50,   "APOLLO_API_KEY"),
    ("apollo",      "data",   "org_search",   1, "credits",   None, "none",    50,   "APOLLO_API_KEY"),
    ("apollo",      "data",   "enrichment",   1, "credits",   None, "none",    50,   "APOLLO_API_KEY"),
    ("hunter",      "email",  "email_verify", 1, "account",   None, "none",    None, "HUNTER_API_KEY"),
    ("hunter",      "email",  "email_find",   1, "account",   None, "none",    None, "HUNTER_API_KEY"),
    ("abstract",    "email",  "email_verify", 2, "credits",   100,  "monthly", None, "ABSTRACT_API_KEY"),
    ("local_smtp",  "email",  "email_verify", 3, "unlimited", None, "none",    None, None),
]

ACTIVE = "active"
EXHAUSTED = "exhausted"
COOLDOWN = "cooldown"
UNAVAILABLE = "unavailable"


class Registry:
    def __init__(self, db):
        self.db = db

    def seed_if_empty(self):
        if self.db.one("SELECT 1 FROM providers LIMIT 1"):
            return
        now = utcnow()
        for name, ptype, task, prio, kind, limit, period, rpm, env_key in SEED:
            self.db.execute(
                "INSERT OR REPLACE INTO providers"
                " (name, task, type, priority, quota_kind, quota_limit, quota_used,"
                "  period, period_start, rpm_limit, status, env_key, notes)"
                " VALUES (?,?,?,?,?,?,0,?,?,?,'active',?,NULL)",
                (name, task, ptype, prio, kind, limit, period, now, rpm, env_key),
            )

    # ------------------------------------------------------------------ read
    def providers_for_task(self, task: str, key_counts: dict = None):
        """key_counts: provider name -> number of pooled keys; the effective
        quota is base limit x key count (5 Tavily keys = 5000 credits)."""
        key_counts = key_counts or {}
        rows = self.db.query(
            "SELECT * FROM providers WHERE task = ? ORDER BY priority ASC", (task,)
        )
        out = []
        now = utcnow()
        for row in rows:
            # monthly quota window rollover
            if row["period"] == "monthly" and row["period_start"]:
                start = row["period_start"][:7]
                if start != now[:7]:
                    self.db.execute(
                        "UPDATE providers SET quota_used = 0, period_start = ?, status='active',"
                        " status_reason=NULL, cooldown_until=NULL WHERE name=? AND task=?",
                        (now, row["name"], row["task"]),
                    )
                    row["quota_used"], row["status"] = 0, ACTIVE
            # cooldown expiry
            if row["status"] == COOLDOWN and row["cooldown_until"] and row["cooldown_until"] <= now:
                self.db.execute(
                    "UPDATE providers SET status='active', cooldown_until=NULL, status_reason=NULL"
                    " WHERE name=? AND task=?",
                    (row["name"], row["task"]),
                )
                row["status"] = ACTIVE
            # key availability (None env_key => local provider)
            load_env()
            has_key = row["env_key"] is None or bool(_env(row["env_key"]))
            multiplier = max(1, key_counts.get(row["name"], 1))
            row["quota_limit_effective"] = (
                row["quota_limit"] * multiplier if row["quota_limit"] is not None else None)
            row["_usable"] = (has_key and row["status"] in (ACTIVE, COOLDOWN)
                              and self._within_quota(row, multiplier))
            out.append(row)
        return out

    @staticmethod
    def _within_quota(row, multiplier: int = 1) -> bool:
        if row["quota_limit"] is None:
            return True
        return (row["quota_used"] or 0) < row["quota_limit"] * max(1, multiplier)

    def status_table(self):
        rows = self.db.query(
            "SELECT name, task, type, priority, quota_kind, quota_limit, quota_used,"
            " period, rpm_limit, status, status_reason, cooldown_until, env_key, base_url, model_name FROM providers"
            " ORDER BY task, priority"
        )
        for row in rows:
            row["has_key"] = row["env_key"] is None or bool(_env(row["env_key"]))
        return rows

    def usage_summary(self):
        return self.db.query(
            "SELECT provider, task, COUNT(*) AS calls, SUM(units) AS units,"
            " AVG(latency_ms) AS avg_latency FROM usage_ledger GROUP BY provider, task"
        )

    # ----------------------------------------------------------------- write
    def record_usage(self, provider, task, job_id, units, unit_kind, status, latency_ms,
                     prompt_tokens=0, completion_tokens=0, key_index=None):
        self.db.execute(
            "INSERT INTO usage_ledger (ts, provider, task, job_id, units, unit_kind, status,"
            " latency_ms, prompt_tokens, completion_tokens, key_index)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (utcnow(), provider, task, job_id, units, unit_kind, status, latency_ms,
             int(prompt_tokens or 0), int(completion_tokens or 0), key_index),
        )

    def add_quota_used(self, provider, task, units, multiplier: int = 1):
        self.db.execute(
            "UPDATE providers SET quota_used = COALESCE(quota_used, 0) + ? WHERE name=? AND task=?",
            (units, provider, task),
        )
        row = self.db.one(
            "SELECT quota_limit, quota_used FROM providers WHERE name=? AND task=?",
            (provider, task),
        )
        if row and row["quota_limit"] is not None and \
                (row["quota_used"] or 0) >= row["quota_limit"] * max(1, multiplier):
            self.mark(provider, task, EXHAUSTED, "quota_limit reached")

    def mark(self, provider, task, status, reason=None, cooldown_seconds=None):
        until = None
        if cooldown_seconds:
            until = (datetime.now(timezone.utc) + timedelta(seconds=cooldown_seconds)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        cur = self.db.execute(
            "UPDATE providers SET status=?, status_reason=?, cooldown_until=? WHERE name=? AND task=?",
            (status, reason, until, provider, task),
        )
        return cur.rowcount > 0

    def count_recent_requests(self, provider, window_seconds=60):
        since = (datetime.now(timezone.utc) - timedelta(seconds=window_seconds)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        row = self.db.one(
            "SELECT COUNT(*) AS n FROM usage_ledger WHERE provider=? AND ts >= ?",
            (provider, since),
        )
        return row["n"] if row else 0

    def set_rpm_from_headers(self, provider, task, remaining):
        """Proactive: if a provider header says 0 remaining, mark cooldown now
        instead of waiting for the next 429."""
        if remaining is not None and remaining <= 0:
            self.mark(provider, task, COOLDOWN, "provider headers report 0 remaining", 60)


def _env(name):
    import os

    return os.environ.get(name)
