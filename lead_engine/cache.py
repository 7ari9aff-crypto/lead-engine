"""Three-level cache:

L1 request cache  — same exact query, short TTL (search results etc.)
L2 entity cache   — company/contact facts, long TTL
L3 evidence cache — append-only claims with source + timestamp

TTLs come from config/cache_policy.yaml, never hard-coded here.
"""
import hashlib
import json

from .config import ttl_seconds
from .db import utcnow


def _now_plus(seconds: int) -> str:
    from datetime import datetime, timedelta, timezone

    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


class CacheLayer:
    def __init__(self, db, policy: dict):
        self.db = db
        self.policy = policy or {}

    # ------------------------------------------------------------------ keys
    @staticmethod
    def make_key(task, payload) -> str:
        blob = json.dumps({"task": task, "payload": payload}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha1(blob.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------- L1 request
    def get_request(self, task, payload):
        key = self.make_key(task, payload)
        row = self.db.one(
            "SELECT payload, expires_at FROM cache WHERE level=1 AND cache_key=?", (key,)
        )
        if not row or row["expires_at"] <= utcnow():
            return None
        return json.loads(row["payload"])

    def put_request(self, task, payload, result, data_type="search_results"):
        key = self.make_key(task, payload)
        self.db.execute(
            "INSERT OR REPLACE INTO cache (level, cache_key, payload, data_type, created_at, expires_at)"
            " VALUES (1,?,?,?,?,?)",
            (key, json.dumps(result, ensure_ascii=False), data_type, utcnow(),
             _now_plus(ttl_seconds(self.policy, data_type))),
        )

    # ------------------------------------------------------------- L2 entity
    def get_entity(self, entity_type, identity):
        key = self.make_key("entity:" + entity_type, identity)
        row = self.db.one(
            "SELECT payload, expires_at FROM cache WHERE level=2 AND cache_key=?", (key,)
        )
        if not row or row["expires_at"] <= utcnow():
            return None
        return json.loads(row["payload"])

    def put_entity(self, entity_type, identity, data, data_type="company_name"):
        key = self.make_key("entity:" + entity_type, identity)
        self.db.execute(
            "INSERT OR REPLACE INTO cache (level, cache_key, payload, data_type, created_at, expires_at)"
            " VALUES (2,?,?,?,?,?)",
            (key, json.dumps(data, ensure_ascii=False), data_type, utcnow(),
             _now_plus(ttl_seconds(self.policy, data_type))),
        )

    # ---------------------------------------------------------- L3 evidence
    def add_evidence(self, db, lead_id, claim, source, method, data_type="evidence"):
        db.add_evidence(lead_id, claim, source, method, _now_plus(ttl_seconds(self.policy, data_type)))

    def purge_expired(self) -> int:
        cur = self.db.execute("DELETE FROM cache WHERE expires_at <= ?", (utcnow(),))
        return cur.rowcount
