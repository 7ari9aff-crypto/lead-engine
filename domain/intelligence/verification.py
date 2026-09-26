"""Verification rules (pure). Locked semantics:

- CATCH_ALL ≠ DELIVERABLE.
- UNKNOWN must never be promoted to DELIVERABLE without new evidence.
- Historical records are never overwritten (new record per verification).
"""
from __future__ import annotations

from domain.shared.types import VerificationStatus


def promote(previous: VerificationStatus, new: VerificationStatus, evidence: dict) -> VerificationStatus:
    """Decide which status survives when new evidence arrives.

    DELIVERABLE requires direct evidence (smtp accepted or provider verified).
    A catch-all domain stays CATCH_ALL regardless of provider optimism.
    UNKNOWN never becomes DELIVERABLE unless evidence carries an explicit
    accepted-by-smtp marker.
    """
    if previous is VerificationStatus.DELIVERABLE:
        return VerificationStatus.DELIVERABLE          # never downgrade silently
    if new is VerificationStatus.DELIVERABLE:
        if previous is VerificationStatus.CATCH_ALL and not evidence.get("smtp_accepted"):
            return VerificationStatus.CATCH_ALL        # catch-all ≠ deliverable
        if not evidence.get("provider_verified") and not evidence.get("smtp_accepted"):
            return VerificationStatus.UNKNOWN          # no evidence → no promotion
    return new


def qualification_worthiness(status: VerificationStatus) -> str:
    """How a verification status maps into qualification inputs."""
    return {
        VerificationStatus.DELIVERABLE: "usable",
        VerificationStatus.RISKY: "usable_with_risk",
        VerificationStatus.CATCH_ALL: "weak",
        VerificationStatus.UNKNOWN: "weak",
        VerificationStatus.INVALID: "unusable",
    }[status]


def mask_email(local: str, domain: str) -> str:
    """Masked display form: keeps the mailbox shape without exposing PII."""
    if len(local) <= 2:
        local_masked = local[0] + "*"
    else:
        local_masked = local[0] + "***" + local[-1]
    return f"{local_masked}@{domain}"
