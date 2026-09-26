"""Deterministic scoring + qualification rules (pure). AI may interpret and
propose; the final qualification decision runs through these contracts
(architecture §27, §49: Evidence > AI Guess).

Scoring v1: deterministic weights over evidence quality, contact quality and
verification status. Historical scoring_records are never overwritten.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from domain.shared.types import QualificationDecision, VerificationStatus

SCORE_VERSION = "v1"
POLICY_VERSION = "default-v1"


@dataclass(frozen=True)
class ScoreInputs:
    has_website: bool = False
    has_phone_claim: bool = False
    observation_count: int = 0
    distinct_source_count: int = 0
    best_email_status: VerificationStatus | None = None
    intent_signal_count: int = 0
    icp_city_match: bool = False


@dataclass(frozen=True)
class ScoreResult:
    score: float
    version: str = SCORE_VERSION
    explanations: list[str] = field(default_factory=list)


def compute_score(inputs: ScoreInputs) -> ScoreResult:
    score = 0.0
    explanations: list[str] = []

    if inputs.has_website:
        score += 20
        explanations.append("website found (+20)")
    if inputs.best_email_status is VerificationStatus.DELIVERABLE:
        score += 25
        explanations.append("deliverable email (+25)")
    elif inputs.best_email_status in (VerificationStatus.RISKY, VerificationStatus.CATCH_ALL):
        score += 10
        explanations.append("usable-with-risk email (+10)")
    if inputs.has_phone_claim:
        score += 15
        explanations.append("phone claim (+15)")
    score += min(inputs.distinct_source_count, 3) * 5
    if inputs.distinct_source_count:
        explanations.append(f"distinct sources x{min(inputs.distinct_source_count, 3)} (+{min(inputs.distinct_source_count, 3) * 5})")
    if inputs.observation_count >= 3:
        score += 10
        explanations.append("evidence-rich observation set (+10)")
    if inputs.intent_signal_count:
        score += min(inputs.intent_signal_count, 2) * 5
        explanations.append(f"intent signals x{min(inputs.intent_signal_count, 2)}")
    if inputs.icp_city_match:
        score += 5
        explanations.append("ICP city match (+5)")

    return ScoreResult(score=round(min(score, 100.0), 1), explanations=explanations)


@dataclass(frozen=True)
class QualificationInputs:
    score: float
    domain: str | None
    email_status: VerificationStatus | None
    suppressed: bool = False
    policy_decision: str = "ALLOWED"        # ALLOWED | BLOCKED | NEEDS_REVIEW
    country: str | None = None


def decide(inputs: QualificationInputs) -> tuple[QualificationDecision, list[str]]:
    """Deterministic-first qualification: hard filters, policy gate, then score."""
    reasons: list[str] = []

    if inputs.suppressed:
        reasons.append("subject suppressed by governance")
        return QualificationDecision.REJECTED, reasons
    if inputs.policy_decision == "BLOCKED":
        reasons.append("policy blocked the operation")
        return QualificationDecision.REJECTED, reasons
    if inputs.email_status is VerificationStatus.INVALID:
        reasons.append("email verification returned INVALID")
        return QualificationDecision.REJECTED, reasons
    if not inputs.domain:
        reasons.append("no resolvable business identity (no domain)")
        return QualificationDecision.REVIEW, reasons

    if inputs.policy_decision == "NEEDS_REVIEW":
        reasons.append("policy requires human review")
        return QualificationDecision.REVIEW, reasons

    if inputs.score >= 60:
        reasons.append(f"score {inputs.score} >= 60 acceptance threshold")
        return QualificationDecision.ACCEPTED, reasons
    if inputs.score >= 35:
        reasons.append(f"score {inputs.score} within review band 35..59")
        return QualificationDecision.REVIEW, reasons
    reasons.append(f"score {inputs.score} below review band")
    return QualificationDecision.REJECTED, reasons
