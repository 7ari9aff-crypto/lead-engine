"""Truth Layer — the canonical fact store behind the research agent.

The model is NOT the source of truth. Every claim the agent (or the legacy
pipeline) produces lands here as a *fact* with:

- value + exact status: VERIFIED | CONFLICTED | STALE | UNVERIFIED | INFERRED
  (nothing in between — "probably true" is not a system state)
- provenance: one row per source in fact_sources (url / provider / query / quote)
- freshness: collected_at + expires_at (TTLs from config/cache_policy.yaml);
  expired facts read back as STALE — a cache hit never becomes a fresh fact
- conflicts: two fresh values for the same field -> both CONFLICTED + an OPEN
  row in fact_conflicts. Resolution is explicit (auto by stronger source or
  human) and recorded with who/when/why; unresolved conflicts stay OPEN.

Engine tables (bare names resolve to `engine` on Postgres via the pinned
search_path, and to the local file on SQLite) — no _t() needed here.
"""
import json
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from .config import load_cache_policy
from .db import utcnow

STATUS_VERIFIED = "VERIFIED"
STATUS_CONFLICTED = "CONFLICTED"
STATUS_STALE = "STALE"
STATUS_UNVERIFIED = "UNVERIFIED"
STATUS_INFERRED = "INFERRED"

# Verification rank used to pick the "current" value of a field.
_RANK = {STATUS_VERIFIED: 3, STATUS_UNVERIFIED: 2, STATUS_INFERRED: 1,
         STATUS_CONFLICTED: 0, STATUS_STALE: -1}

# field name -> cache_policy data_type (TTL days). Fields not listed use
# website_content's TTL — deliberately short so unstated freshness decays.
FIELD_TTL_MAP = {
    "email": "email",
    "phone": "phone",
    "decision_maker": "decision_maker",
    "decision_maker_title": "decision_maker",
    "linkedin": "decision_maker",
    "domain": "company_domain",
    "website": "company_domain",
    "employee_count": "employee_estimate",
    "branches": "employee_estimate",
    "industry": "industry",
    "city": "location",
    "country": "location",
    "address": "location",
}

SOURCE_KINDS = ("search_api", "openmanus", "apollo", "hunter", "abstract",
                "email_verify", "manual", "llm_inference")


def _now_plus(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _domain_of(url: str | None, provider: str | None) -> str:
    """Independent-source key: hostname when there is a URL, else the provider
    identity. Two facts from the same domain do NOT verify each other."""
    if url:
        host = (urlparse(url).hostname or "").lower().removeprefix("www.")
        if host:
            return host
    return f"provider:{provider or 'unknown'}"


class FactsStore:
    def __init__(self, db, cache_policy: dict | None = None):
        self.db = db
        self.policy = cache_policy or load_cache_policy()
        self._sqlite = getattr(db, "dialect", "sqlite") == "sqlite"

    # ------------------------------------------------------------- helpers
    def _org(self):
        org = getattr(self.db, "org_id", None)
        if self._sqlite:
            return org or "shared"
        return org  # PG: the adapter injects org on INSERT; None = platform row

    def _org_eq(self, column: str = "organization_id") -> tuple[str, list]:
        """WHERE fragment pinning reads to the caller's org. On SQLite every
        row has a concrete org ('shared' default); on PG NULL org rows are
        platform rows the agent must not mix into tenant snapshots."""
        org = getattr(self.db, "org_id", None)
        if self._sqlite:
            return f" AND {column} = ?", [org or "shared"]
        if org:
            return f" AND {column} = ?", [org]
        return f" AND {column} IS NULL", []

    def _ttl_days(self, field: str) -> int:
        days = (self.policy.get("ttl_days") or {})
        return int(days.get(FIELD_TTL_MAP.get(field, "website_content"), 7))

    @staticmethod
    def _fact_id() -> str:
        return f"fact_{uuid.uuid4().hex[:12]}"

    # ------------------------------------------------------------- record
    def record_fact(self, subject_kind: str, subject_id: str, field: str,
                    value, *, source_url: str | None = None,
                    source_kind: str = "search_api", provider: str | None = None,
                    query: str | None = None, quote: str | None = None,
                    job_id: str | None = None, run_id: str | None = None,
                    value_kind: str = "text", confidence: float | None = None,
                    inferred: bool = False) -> dict:
        """Record one observation about one subject field.

        Same value -> the fact is freshened (new source appended, clock reset).
        Different fresh value -> BOTH become CONFLICTED with an OPEN conflict
        row; nothing is silently overwritten. Different stale value -> the new
        fact simply supersedes (the old one is already STALE).
        inferred=True (no source) records the INFERRED state with its rationale
        expected in `quote`.
        """
        value = "" if value is None else str(value).strip()
        if not value:
            raise ValueError("fact value must be non-empty")
        org = self._org()
        now = utcnow()

        existing = self.db.one(
            "SELECT * FROM research_facts WHERE subject_kind=? AND subject_id=?"
            " AND field=? AND value=?" + self._org_eq()[0],
            (subject_kind, subject_id, field, value, *self._org_eq()[1]))

        if existing:
            fact_id = existing["fact_id"]
            if source_url or provider:
                self._add_source(fact_id, org, source_url, source_kind, provider,
                                 query, quote)
            status, conf = self._recompute_status(fact_id, None)
            self.db.execute(
                "UPDATE research_facts SET status=?, confidence=?, collected_at=?,"
                " expires_at=?, updated_at=? WHERE fact_id=?",
                (status, conf if conf is not None else existing["confidence"],
                 now, self._fresh_until(existing, now) or existing.get("expires_at"),
                 now, fact_id))
            return self.get_fact(fact_id)

        # brand-new value
        if inferred:
            status, conf = STATUS_INFERRED, (confidence if confidence is not None else 0.3)
        else:
            status, conf = STATUS_UNVERIFIED, (confidence if confidence is not None else 0.5)
        fact_id = self._fact_id()
        expires_at = _now_plus(self._ttl_days(field)) if not inferred else None
        self.db.execute(
            "INSERT INTO research_facts (fact_id, organization_id, subject_kind,"
            " subject_id, field, value, value_kind, status, confidence, job_id,"
            " run_id, collected_at, expires_at, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (fact_id, org, subject_kind, subject_id, field, value, value_kind,
             status, conf, job_id, run_id, now, expires_at, now, now))
        if source_url or provider:
            self._add_source(fact_id, org, source_url, source_kind, provider,
                             query, quote)
        else:
            self._add_source(fact_id, org, None, "llm_inference", provider, query,
                             quote or "inferred without a direct source")

        # conflict detection against OTHER fresh values of the same field
        others, params = [], []
        sql = ("SELECT * FROM research_facts WHERE subject_kind=? AND subject_id=?"
               " AND field=? AND fact_id<>? AND status IN ('VERIFIED','UNVERIFIED','CONFLICTED')")
        params.extend((subject_kind, subject_id, field, fact_id))
        org_sql, org_params = self._org_eq()
        sql += org_sql
        params.extend(org_params)
        for other in self.db.query(sql, params):
            if self._is_fresh(other, now):
                self._open_conflict(org, subject_kind, subject_id, field,
                                    other["fact_id"], fact_id, job_id)
        status, conf = self._recompute_status(fact_id, None)
        self.db.execute(
            "UPDATE research_facts SET status=?, confidence=?, updated_at=? WHERE fact_id=?",
            (status, conf if conf is not None else 0.5, now, fact_id))
        return self.get_fact(fact_id)

    # ---------------------------------------------------------- conflicts
    def _open_conflict(self, org, subject_kind, subject_id, field,
                       fact_a: str, fact_b: str, job_id: str | None) -> str | None:
        pair = {fact_a, fact_b}
        for row in self.conflicts(subject_kind=subject_kind, subject_id=subject_id,
                                  field=field, status="OPEN"):
            if {row["fact_a"], row["fact_b"]} == pair:
                return row["conflict_id"]
        conflict_id = f"cfl_{uuid.uuid4().hex[:12]}"
        now = utcnow()
        self.db.execute(
            "INSERT INTO fact_conflicts (conflict_id, organization_id, subject_kind,"
            " subject_id, field, fact_a, fact_b, resolution, job_id, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,'OPEN',?,?,?)",
            (conflict_id, org, subject_kind, subject_id, field, fact_a, fact_b,
             job_id, now, now))
        for fid in pair:
            self.db.execute(
                "UPDATE research_facts SET status=?, updated_at=? WHERE fact_id=?",
                (STATUS_CONFLICTED, now, fid))
        return conflict_id

    def conflicts(self, subject_kind: str | None = None,
                  subject_id: str | None = None, field: str | None = None,
                  status: str = "OPEN") -> list[dict]:
        sql, params = "SELECT * FROM fact_conflicts WHERE 1=1", []
        if subject_kind:
            sql += " AND subject_kind=?"
            params.append(subject_kind)
        if subject_id:
            sql += " AND subject_id=?"
            params.append(subject_id)
        if field:
            sql += " AND field=?"
            params.append(field)
        if status:
            sql += " AND resolution=?"
            params.append(status)
        org_sql, org_params = self._org_eq()
        sql += org_sql
        params.extend(org_params)
        return self.db.query(sql + " ORDER BY created_at DESC", params)

    def resolve_conflict(self, conflict_id: str, winner_fact_id: str,
                         *, note: str | None = None, by: str | None = None,
                         automatic: bool = False) -> dict:
        """Resolve one conflict: winner -> VERIFIED, loser -> STALE. Recorded
        with who/when/why; nothing is deleted (audit-friendly)."""
        row = self.db.one("SELECT * FROM fact_conflicts WHERE conflict_id=?",
                          (conflict_id,))
        if not row:
            raise ValueError(f"conflict not found: {conflict_id}")
        if winner_fact_id not in (row["fact_a"], row["fact_b"]):
            raise ValueError("winner must be one of the conflicting facts")
        loser = row["fact_b"] if winner_fact_id == row["fact_a"] else row["fact_a"]
        now = utcnow()
        self.db.execute(
            "UPDATE fact_conflicts SET resolution=?, resolution_note=?, resolved_by=?,"
            " resolved_at=?, winner=?, updated_at=? WHERE conflict_id=?",
            ("RESOLVED_AUTO" if automatic else "RESOLVED_HUMAN",
             note, by, now, winner_fact_id, now, conflict_id))
        self.db.execute(
            "UPDATE research_facts SET status=?, confidence=MAX(confidence, 0.85),"
            " updated_at=? WHERE fact_id=?", (STATUS_VERIFIED, now, winner_fact_id))
        self.db.execute(
            "UPDATE research_facts SET status=?, updated_at=? WHERE fact_id=?",
            (STATUS_STALE, now, loser))
        return self.db.one("SELECT * FROM fact_conflicts WHERE conflict_id=?",
                           (conflict_id,))

    # -------------------------------------------------------- verification
    def verify_fact(self, fact_id: str, *, outcome: str = "verified",
                    confidence: float | None = None, source_url: str | None = None,
                    provider: str | None = None, quote: str | None = None) -> dict:
        """Apply an explicit verification result to a fact.

        outcome 'verified' -> VERIFIED. 'refuted' -> STALE with the refutation
        quoted (the value is no longer current knowledge, and the trail keeps
        WHY). Anything else leaves the fact untouched and returns it as-is.
        """
        fact = self.get_fact(fact_id)
        if not fact:
            raise ValueError(f"fact not found: {fact_id}")
        now = utcnow()
        if source_url or provider:
            self._add_source(fact_id, fact["organization_id"], source_url,
                             "email_verify", provider, None, quote)
        if outcome == "verified":
            conf = confidence if confidence is not None else max(0.85, fact["confidence"] or 0)
            self.db.execute(
                "UPDATE research_facts SET status=?, confidence=?, expires_at=?,"
                " updated_at=? WHERE fact_id=?",
                (STATUS_VERIFIED, conf, _now_plus(self._ttl_days(fact["field"])),
                 now, fact_id))
        elif outcome == "refuted":
            self.db.execute(
                "UPDATE research_facts SET status=?, confidence=?, updated_at=?"
                " WHERE fact_id=?", (STATUS_STALE, 0.1, now, fact_id))
        return self.get_fact(fact_id)

    # ------------------------------------------------------------ reading
    def get_fact(self, fact_id: str) -> dict | None:
        row = self.db.one("SELECT * FROM research_facts WHERE fact_id=?", (fact_id,))
        if row:
            row["sources"] = self.sources_for(fact_id)
        return row

    def sources_for(self, fact_id: str) -> list[dict]:
        return self.db.query(
            "SELECT * FROM fact_sources WHERE fact_id=? ORDER BY id", (fact_id,))

    def _add_source(self, fact_id, org, url, kind, provider, query, quote):
        self.db.execute(
            "INSERT INTO fact_sources (organization_id, fact_id, source_url,"
            " source_kind, provider, query, quote, collected_at) VALUES (?,?,?,?,?,?,?,?)",
            (org, fact_id, url, kind if kind in SOURCE_KINDS else "search_api",
             provider, query, quote, utcnow()))

    def _is_fresh(self, fact: dict, now: str | None = None) -> bool:
        exp = fact.get("expires_at")
        return not exp or exp > (now or utcnow())

    def _fresh_until(self, fact: dict, now: str) -> str | None:
        if not self._is_fresh(fact, now):
            return None
        return fact.get("expires_at") or _now_plus(
            self._ttl_days(fact["field"]))

    def _recompute_status(self, fact_id: str, field_based_status) -> tuple[str, float | None]:
        """VERIFIED when 2+ independent sources agree; UNVERIFIED with one;
        INFERRED stays until a source arrives; CONFLICTED overrides all."""
        row = self.db.one("SELECT * FROM research_facts WHERE fact_id=?", (fact_id,))
        if not row:
            return STATUS_UNVERIFIED, None
        sources = self.sources_for(fact_id)
        real = [s for s in sources if s["source_kind"] != "llm_inference"]
        distinct = {_domain_of(s["source_url"], s["provider"]) for s in real}
        if row["status"] == STATUS_CONFLICTED and self._has_open_conflict(fact_id):
            return STATUS_CONFLICTED, row["confidence"]
        if len(distinct) >= 2:
            return STATUS_VERIFIED, min(0.95, 0.5 + 0.15 * (len(distinct) - 1))
        if real:
            return STATUS_UNVERIFIED, row["confidence"]
        return STATUS_INFERRED, row["confidence"]

    def _has_open_conflict(self, fact_id: str) -> bool:
        row = self.db.one(
            "SELECT 1 AS ok FROM fact_conflicts WHERE resolution='OPEN'"
            " AND (fact_a=? OR fact_b=?) LIMIT 1", (fact_id, fact_id))
        return bool(row)

    def _apply_freshness(self, facts: list[dict]) -> list[dict]:
        now = utcnow()
        for f in facts:
            if f["status"] in (STATUS_VERIFIED, STATUS_UNVERIFIED, STATUS_CONFLICTED) \
                    and not self._is_fresh(f, now):
                self.db.execute(
                    "UPDATE research_facts SET status=?, updated_at=? WHERE fact_id=?",
                    (STATUS_STALE, now, f["fact_id"]))
                f["status"] = STATUS_STALE
        return facts

    def snapshot(self, subject_kind: str, subject_id: str) -> dict:
        """The presentation-grade view of one subject: per field the current
        value + status + provenance + freshness, alternatives when conflicted,
        and the full source trail. This — not the LLM — is what the UI and the
        qualification layer trust."""
        sql = ("SELECT * FROM research_facts WHERE subject_kind=? AND subject_id=?")
        params = [subject_kind, subject_id]
        org_sql, org_params = self._org_eq()
        sql += org_sql
        params.extend(org_params)
        facts = self._apply_freshness(self.db.query(sql + " ORDER BY collected_at DESC", params))
        open_conflicts = self.conflicts(subject_kind=subject_kind,
                                        subject_id=subject_id, status="OPEN")
        conflicted_fact_ids = set()
        for c in open_conflicts:
            conflicted_fact_ids.update((c["fact_a"], c["fact_b"]))

        by_field: dict[str, list[dict]] = {}
        for f in facts:
            f["sources"] = self.sources_for(f["fact_id"])
            by_field.setdefault(f["field"], []).append(f)

        fields = {}
        for field, group in by_field.items():
            fresh = [f for f in group if f["status"] != STATUS_STALE] or group
            fresh.sort(key=lambda f: (_RANK.get(f["status"], 0), f["confidence"] or 0,
                                      f["collected_at"]), reverse=True)
            current = fresh[0]
            field_status = current["status"]
            if any(f["fact_id"] in conflicted_fact_ids for f in group):
                field_status = STATUS_CONFLICTED
            fields[field] = {
                "value": current["value"],
                "value_kind": current["value_kind"],
                "status": field_status,
                "confidence": current["confidence"],
                "collected_at": current["collected_at"],
                "expires_at": current["expires_at"],
                "fact_id": current["fact_id"],
                "sources": current["sources"],
                "alternatives": [
                    {"value": f["value"], "status": f["status"], "fact_id": f["fact_id"],
                     "sources": f["sources"]}
                    for f in fresh[1:] if f["status"] != STATUS_STALE
                ],
            }
        return {
            "subject_kind": subject_kind,
            "subject_id": subject_id,
            "fields": fields,
            "conflicts": open_conflicts,
            "stale_fields": sorted(
                f["field"] for f in facts if f["status"] == STATUS_STALE),
        }

    def facts_for_qualification(self, subject_kind: str, subject_id: str) -> dict:
        """Flat, deterministic input for the qualification layer: current values
        + their statuses + which fields are conflicted/stale. The qualifier must
        reason over THIS, never over its own memory."""
        snap = self.snapshot(subject_kind, subject_id)
        values = {k: v["value"] for k, v in snap["fields"].items()}
        statuses = {k: v["status"] for k, v in snap["fields"].items()}
        return {
            "values": values,
            "statuses": statuses,
            "conflicted": sorted(k for k, s in statuses.items() if s == STATUS_CONFLICTED),
            "stale": snap["stale_fields"],
        }

    # ------------------------------------------------- research context
    def add_visit(self, job_id: str, url: str, title: str | None = None,
                  http_status: int | None = None, summary: str | None = None) -> None:
        org = self._org()
        existing = self.db.one("SELECT id FROM visited_sources WHERE job_id=? AND url=?",
                               (job_id, url))
        if existing:
            self.db.execute(
                "UPDATE visited_sources SET title=?, http_status=?, summary=?,"
                " fetched_at=? WHERE id=?",
                (title, http_status, summary, utcnow(), existing["id"]))
            return
        self.db.execute(
            "INSERT INTO visited_sources (organization_id, job_id, url, title,"
            " http_status, summary, fetched_at) VALUES (?,?,?,?,?,?,?)",
            (org, job_id, url, title, http_status, summary, utcnow()))

    def visited(self, job_id: str) -> list[dict]:
        sql, params = "SELECT * FROM visited_sources WHERE job_id=?", [job_id]
        org_sql, org_params = self._org_eq()
        return self.db.query(sql + org_sql + " ORDER BY fetched_at",
                             params + org_params)

    def add_open_question(self, job_id: str, question: str,
                          subject_kind: str = "company",
                          subject_id: str | None = None) -> int:
        cur = self.db.execute(
            "INSERT INTO open_questions (organization_id, job_id, subject_kind,"
            " subject_id, question, status, created_at) VALUES (?,?,?,?,?,'OPEN',?)",
            (self._org(), job_id, subject_kind, subject_id, question, utcnow()))
        return cur.lastrowid

    def answer_open_question(self, question_id: int, fact_id: str) -> None:
        self.db.execute(
            "UPDATE open_questions SET status='ANSWERED', answer_fact_id=?,"
            " answered_at=? WHERE id=? AND status='OPEN'",
            (fact_id, utcnow(), question_id))

    def drop_open_question(self, question_id: int) -> None:
        self.db.execute(
            "UPDATE open_questions SET status='DROPPED', answered_at=?"
            " WHERE id=? AND status='OPEN'", (utcnow(), question_id))

    def open_questions(self, job_id: str, status: str = "OPEN") -> list[dict]:
        sql, params = ("SELECT * FROM open_questions WHERE job_id=? AND status=?",
                       [job_id, status])
        org_sql, org_params = self._org_eq()
        return self.db.query(sql + org_sql + " ORDER BY id", params + org_params)

    # ------------------------------------------------------------ export
    def export_subject(self, subject_kind: str, subject_id: str) -> dict:
        """Full auditable dump: facts + every source + conflicts + visits."""
        snap = self.snapshot(subject_kind, subject_id)
        all_sources = []
        for field in snap["fields"].values():
            all_sources.extend(field["sources"])
        return {**snap, "all_sources": all_sources}
