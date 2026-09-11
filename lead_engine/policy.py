"""Outreach safety gate: suppression + channel policy + risk throttles.

The single decision point every outbound action passes through BEFORE any
provider adapter is reached. Integration adapters answer "how to send";
this layer answers "whether sending is allowed at all".

Decision values: ALLOW | BLOCK | REVIEW — with human-readable reasons and
the full check trace (audit-friendly, no hidden denies).

Domain precursors this builds on (already shipped): the Legal Gate governs
storage, the 5-state email verification prevents bounces at the source, and
the router's quotas are the first risk throttle.
"""
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .db import utcnow

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def _t(db, name: str) -> str:
    """SQLite tests use bare names; Postgres resolves public.* explicitly
    (the engine connection pins search_path=engine)."""
    return name if getattr(db, "dialect", "sqlite") == "sqlite" else f"public.{name}"

ALLOW = "ALLOW"
BLOCK = "BLOCK"
REVIEW = "REVIEW"

# Email statuses that mean "this address will bounce or worse" — the pipeline
# feeds these into suppression automatically.
BOUNCE_STATUSES = {"INVALID"}

DEFAULT_LIMITS = {
    "max_jobs_per_day": 10,
    "max_leads_per_month": 5000,
    "max_provider_calls_per_day": 2000,
    "channels": ["email"],
    "max_sends_per_hour": 200,
}


@dataclass
class Decision:
    decision: str
    reasons: list = field(default_factory=list)
    checks: dict = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.decision == ALLOW


class Suppression:
    """Org-scoped do-not-contact list. One row per (org, channel, value)."""

    @staticmethod
    def normalize(channel: str, value: str) -> tuple[str, str]:
        channel = (channel or "all").strip().lower()
        value = (value or "").strip().lower()
        if channel in ("email", "all") and EMAIL_RE.match(value):
            value = value  # already normalized shape
        return channel, value

    @staticmethod
    def is_suppressed(db, org_id: str, channel: str, value: str) -> tuple[bool, str | None]:
        if not value:
            return False, None
        channel, value = Suppression.normalize(channel, value)
        row = db.one(
            "SELECT reason FROM " + _t(db, "suppression_entries") +
            " WHERE organization_id = ? AND channel IN (?, 'all') AND value = ?"
            " ORDER BY created_at DESC LIMIT 1", (org_id, channel, value))
        return (True, row["reason"]) if row else (False, None)

    @staticmethod
    def add(db, org_id: str, channel: str, value: str, reason: str,
            source: str = "manual") -> dict:
        channel, value = Suppression.normalize(channel, value)
        existing = db.one(
            "SELECT id FROM " + _t(db, "suppression_entries") +
            " WHERE organization_id = ? AND channel = ? AND value = ?",
            (org_id, channel, value))
        if existing:
            db.execute(
                "UPDATE " + _t(db, "suppression_entries") + " SET reason = ?, source = ?,"
                " created_at = ? WHERE id = ?",
                (reason, source, utcnow(), existing["id"]))
            return {"id": existing["id"], "channel": channel, "value": value,
                    "reason": reason, "updated": True}
        db.execute(
            "INSERT INTO " + _t(db, "suppression_entries") +
            " (organization_id, channel, value, reason, source, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (org_id, channel, value, reason, source, utcnow()))
        row = db.one(
            "SELECT id FROM " + _t(db, "suppression_entries") +
            " WHERE organization_id = ? AND channel = ? AND value = ?",
            (org_id, channel, value))
        return {"id": row["id"] if row else None, "channel": channel,
                "value": value, "reason": reason, "created": True}

    @staticmethod
    def remove(db, org_id: str, entry_id: str) -> bool:
        cur = db.execute(
            "DELETE FROM " + _t(db, "suppression_entries") + " WHERE organization_id = ? AND id = ?",
            (org_id, entry_id))
        return getattr(cur, "rowcount", 0) > 0

    @staticmethod
    def suppress_bounced(db, org_id: str, email: str | None,
                         email_status: str | None) -> bool:
        """Pipeline hook: auto-suppress addresses the verifier marked dead."""
        if not email or email_status not in BOUNCE_STATUSES:
            return False
        Suppression.add(db, org_id, "email", email, "bounced", source="pipeline")
        return True


class ChannelPolicy:
    """Which channels the org may use (source: organizations.limits)."""

    @staticmethod
    def allowed_channels(db, org_id: str) -> list[str]:
        row = db.one("SELECT limits FROM " + _t(db, "organizations") + " WHERE id = ?", (org_id,))
        if not row:
            return list(DEFAULT_LIMITS["channels"])
        limits = row.get("limits") or {}
        if isinstance(limits, str):
            import json
            try:
                limits = json.loads(limits)
            except json.JSONDecodeError:
                limits = {}
        return list(limits.get("channels", DEFAULT_LIMITS["channels"]))


class Risk:
    """Volume heuristics. A decision input, not a punisher: HIGH risk routes
    to REVIEW (manual approval) per policy instead of silently failing."""

    @staticmethod
    def level(recent_sends: int, baseline_per_hour: int) -> str:
        if baseline_per_hour <= 0:
            return "UNKNOWN"
        ratio = recent_sends / max(1, baseline_per_hour)
        if ratio > 10:
            return "HIGH"
        if ratio > 3:
            return "MEDIUM"
        return "LOW"


class PolicyGate:
    """evaluate() = the single entry point. Every check is recorded."""

    @staticmethod
    def evaluate(db, org_id: str, channel: str, value: str, *,
                 recent_sends: int = 0, baseline_per_hour: int = 0) -> Decision:
        reasons: list[str] = []
        checks: dict = {}
        decision = ALLOW

        suppressed, reason = Suppression.is_suppressed(db, org_id, channel, value)
        checks["suppression"] = {"suppressed": suppressed, "reason": reason}
        if suppressed:
            decision = BLOCK
            reasons.append(f"suppressed: {reason}")

        channels = ChannelPolicy.allowed_channels(db, org_id)
        channel_ok = channel in channels or "all" in channels
        checks["channel"] = {"channel": channel, "allowed": channel_ok,
                             "org_channels": channels}
        if not channel_ok:
            decision = BLOCK
            reasons.append(f"channel not enabled for this organization: {channel}")

        risk = Risk.level(recent_sends, baseline_per_hour)
        checks["risk"] = {"level": risk,
                          "recent_sends": recent_sends,
                          "baseline_per_hour": baseline_per_hour}
        if risk == "HIGH" and decision == ALLOW:
            decision = REVIEW
            reasons.append("send volume far above baseline — manual review")

        return Decision(decision=decision, reasons=reasons, checks=checks)
