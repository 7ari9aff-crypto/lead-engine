"""Plan entitlements: per-org limits enforced at job start and provider use.

Source of truth: organizations.limits jsonb (see migration 003). Defaults
apply when the org has no explicit limits. Enforcement points:
- enqueue/start a job        -> max_jobs_per_day
- provider calls             -> max_provider_calls_per_day (router hook)
This is NOT billing: subscriptions synchronize these values, they do not
compute them.
"""
import os
from datetime import datetime, timezone

from .policy import DEFAULT_LIMITS, _t


def get_limits(db, org_id: str | None) -> dict:
    if not org_id:
        return dict(DEFAULT_LIMITS)
    row = db.one("SELECT limits FROM " + _t(db, "organizations") + " WHERE id = ?", (org_id,))
    limits = dict(DEFAULT_LIMITS)
    if row and row.get("limits"):
        raw = row["limits"]
        if isinstance(raw, str):
            import json
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = {}
        if isinstance(raw, dict):
            limits.update(raw)
    return limits


def check_job_start(db, org_id: str | None) -> tuple[bool, str | None]:
    """(allowed, reason). Counts jobs created in the UTC day window."""
    if not org_id:
        return True, None
    limits = get_limits(db, org_id)
    max_jobs = int(limits.get("max_jobs_per_day", DEFAULT_LIMITS["max_jobs_per_day"]))
    day_start = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
    row = db.one(
        "SELECT COUNT(*) AS n FROM " + _t(db, "jobs") + " WHERE organization_id = ? AND created_at >= ?",
        (org_id, day_start))
    used = row["n"] if row else 0
    if used >= max_jobs:
        return False, f"daily job limit reached ({used}/{max_jobs})"
    return True, None


def check_provider_call(db, org_id: str | None) -> bool:
    """Router-level guard: daily provider call budget. Soft by design —
    used by the policy gate, never by the discovery pipeline's own flow."""
    if not org_id:
        return True
    limits = get_limits(db, org_id)
    max_calls = int(limits.get("max_provider_calls_per_day",
                               DEFAULT_LIMITS["max_provider_calls_per_day"]))
    day_start = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
    row = db.one(
        "SELECT COUNT(*) AS n FROM " + _t(db, "usage_ledger") +
        " WHERE organization_id = ? AND ts >= ?", (org_id, day_start))
    return (row["n"] if row else 0) < max_calls
