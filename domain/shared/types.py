"""Tenant context and result enums shared by every context."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True)
class TenantContext:
    """The resolved tenant + actor for one request/job step. Every use case
    requires it; nothing in the domain may operate without a tenant."""
    org_id: str
    actor: str                    # user ext id / 'worker' / 'service'
    role: str = "member"          # owner | admin | member | service
    trace_id: str | None = None

    def is_staff(self) -> bool:
        return self.role in ("owner", "admin", "service")


class GovernanceDecision(StrEnum):
    ALLOWED = "ALLOWED"
    BLOCKED = "BLOCKED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class VerificationStatus(StrEnum):
    DELIVERABLE = "DELIVERABLE"
    RISKY = "RISKY"
    CATCH_ALL = "CATCH_ALL"
    INVALID = "INVALID"
    UNKNOWN = "UNKNOWN"


class QualificationDecision(StrEnum):
    ACCEPTED = "accepted"
    REVIEW = "review"
    REJECTED = "rejected"
