"""Governance policy rules (pure). Governance is a HARD GATE: evaluating and
recording a decision is mandatory before any regulated/outbound operation
(architecture §10). The engine is deterministic — AI never mutates policy."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from domain.shared.types import GovernanceDecision


@dataclass(frozen=True)
class PolicyInput:
    operation: str                 # e.g. 'email.outbound', 'data.erase', 'discovery.search'
    country: str | None = None
    subject_kind: str | None = None   # email | domain | company | contact
    subject_value: str | None = None
    context: dict[str, Any] | None = None


VERSION = "default-v1"


def evaluate(rules: dict[str, Any], inp: PolicyInput) -> tuple[GovernanceDecision, str, str]:
    """Return (decision, legal_basis, reason). Deterministic; first match wins.

    Rule schema (JSONB in governance.legal_policy_versions.rules):
      {"blocked_operations": [...], "review_operations": [...],
       "blocked_countries": [...], "require_country_allowlist": bool,
       "country_allowlist": [...], "suppressed_domains": [...]}
    """
    context = inp.context or {}

    if inp.operation in (rules.get("blocked_operations") or []):
        return GovernanceDecision.BLOCKED, "prohibited-operation", f"{inp.operation} is blocked by policy"

    if inp.subject_kind == "domain" and inp.subject_value:
        domain = inp.subject_value.lower()
        suppressed = rules.get("suppressed_domains") or []
        if any(domain == d or domain.endswith("." + d) for d in suppressed):
            return GovernanceDecision.BLOCKED, "suppression", f"domain {domain} is suppressed"

    if inp.operation in (rules.get("review_operations") or []):
        return GovernanceDecision.NEEDS_REVIEW, "regulated-operation", f"{inp.operation} requires human review"

    blocked_countries = rules.get("blocked_countries") or []
    if inp.country and inp.country.upper() in {c.upper() for c in blocked_countries}:
        return GovernanceDecision.BLOCKED, "restricted-region", f"country {inp.country} is restricted"

    if rules.get("require_country_allowlist"):
        allow = {c.upper() for c in (rules.get("country_allowlist") or [])}
        target = (inp.country or context.get("target_country") or "").upper()
        # Fail-closed: an UNKNOWN country is not allowlisted either. A hard
        # gate that opens when the input is missing is not a gate.
        if target not in allow:
            return (GovernanceDecision.BLOCKED, "region-allowlist",
                    f"country {target or 'unknown'} not allowlisted")

    return GovernanceDecision.ALLOWED, "general-basis", "allowed by default policy"


def default_rules() -> dict[str, Any]:
    return {
        "blocked_operations": ["email.outbound_without_approval"],
        "review_operations": ["email.outbound"],
        "blocked_countries": [],
        "require_country_allowlist": False,
        "country_allowlist": [],
        "suppressed_domains": ["gov", "edu", "mil"],
    }
