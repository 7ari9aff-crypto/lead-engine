"""Pure domain logic tests — no database, no infrastructure."""
from __future__ import annotations

from domain.acquisition.company import (
    domain_from_url,
    is_social,
    looks_editorial,
    normalize_name,
    resolve_identity,
)
from domain.acquisition.icp import build_query_plan, is_empty_plan
from domain.governance.policy import GovernanceDecision, PolicyInput, evaluate
from domain.intelligence.scoring import QualificationInputs, compute_score, decide
from domain.intelligence.verification import VerificationStatus, mask_email, promote
from domain.shared.types import QualificationDecision


def test_verification_without_evidence_never_promotes():
    status = promote(VerificationStatus.UNKNOWN, VerificationStatus.DELIVERABLE, {})
    assert status is VerificationStatus.UNKNOWN  # no evidence → no promotion


def test_catch_all_requires_smtp_even_with_provider_evidence():
    status = promote(VerificationStatus.UNKNOWN, VerificationStatus.DELIVERABLE,
                     {"provider_verified": True})
    assert status is VerificationStatus.DELIVERABLE  # explicit provider evidence
    status = promote(VerificationStatus.CATCH_ALL, VerificationStatus.DELIVERABLE,
                     {"provider_verified": True})
    assert status is VerificationStatus.CATCH_ALL    # catch-all ≠ deliverable


def test_verification_smtp_evidence_promotes():
    status = promote(VerificationStatus.CATCH_ALL, VerificationStatus.DELIVERABLE,
                     {"smtp_accepted": True})
    assert status is VerificationStatus.DELIVERABLE


def test_verification_never_downgrades_deliverable():
    status = promote(VerificationStatus.DELIVERABLE, VerificationStatus.INVALID, {})
    assert status is VerificationStatus.DELIVERABLE


def test_mask_email_hides_mailbox():
    assert mask_email("info", "alpha-dental.sa") == "i***o@alpha-dental.sa"
    assert "*" in mask_email("ab", "x.sa")


def test_scoring_is_deterministic_and_bounded():
    from domain.intelligence.scoring import ScoreInputs

    a = compute_score(ScoreInputs(has_website=True, best_email_status=VerificationStatus.DELIVERABLE,
                                  distinct_source_count=2, observation_count=4))
    b = compute_score(ScoreInputs(has_website=True, best_email_status=VerificationStatus.DELIVERABLE,
                                  distinct_source_count=2, observation_count=4))
    assert a.score == b.score and 0 <= a.score <= 100
    assert a.explanations  # explainability is part of the contract


def test_qualification_hard_filters():
    decision, reasons = decide(QualificationInputs(score=90, domain=None,
                                                   email_status=VerificationStatus.DELIVERABLE))
    assert decision is QualificationDecision.REVIEW and reasons

    decision, _ = decide(QualificationInputs(score=90, domain="x.sa",
                                             email_status=VerificationStatus.INVALID))
    assert decision is QualificationDecision.REJECTED

    decision, _ = decide(QualificationInputs(score=10, domain="x.sa",
                                             email_status=None))
    assert decision is QualificationDecision.REJECTED


def test_policy_blocks_suppressed_domain():
    decision, _, _ = evaluate(
        {"suppressed_domains": ["gov.sa"]},
        PolicyInput(operation="lead.qualification", subject_kind="domain",
                    subject_value="clinic.gov.sa"),
    )
    assert decision is GovernanceDecision.BLOCKED


def test_identity_resolution_skips_social_and_editorial():
    assert resolve_identity("page", "https://facebook.com/x", False, False) == "social"
    assert resolve_identity("Best dental clinics 2026", "https://n.com/best-dental",
                            False, False) == "editorial"
    assert resolve_identity("Alpha", "https://alpha.sa", True, False) == "existing"
    assert resolve_identity("Alpha", "https://alpha.sa", False, False) == "new"
    assert domain_from_url("https://www.alpha.sa/en") == "alpha.sa"
    assert is_social("facebook.com")
    assert looks_editorial("Best dental", "https://x.com/blog/a")
    assert normalize_name("  Alpha   Dental ") == "alpha dental"


def test_empty_icp_plan_is_detected():
    plan = build_query_plan({"cities": [], "keywords_en": []})
    assert is_empty_plan(plan)
    full = build_query_plan({"cities": [{"name": "Riyadh", "ar": "الرياض"}],
                             "keywords_en": ["dental clinic"],
                             "v0_limits": {"max_search_queries": 5}})
    assert not is_empty_plan(full)
    assert len(full["queries"]) == 1
