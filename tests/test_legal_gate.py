from lead_engine.pipeline.legal_gate import LegalGate
from lead_engine.config import load_legal_policy

SA = None


def gate():
    return LegalGate(load_legal_policy("sa"))


def test_company_public_data_accepted():
    verdict = gate().evaluate({
        "sources": ["search_api"], "data_types": ["company_public_data"]})
    assert verdict["storage_allowed"] is True
    assert verdict["decision"] == "ACCEPTED"
    assert verdict["retention_days"] == 30


def test_sensitive_data_rejected():
    verdict = gate().evaluate({
        "sources": ["search_api"], "data_types": ["company_public_data", "sensitive_data"]})
    assert verdict["storage_allowed"] is False
    assert verdict["decision"] == "REJECTED"


def test_personal_contact_requires_review():
    verdict = gate().evaluate({
        "sources": ["apollo_api"], "data_types": ["professional_contact", "personal_contact"]})
    assert verdict["storage_allowed"] is True
    assert verdict["requires_review"] is True
    assert verdict["decision"] == "REVIEW"
    assert verdict["retention_days"] == 14  # strictest of the two


def test_unknown_source_default_deny():
    verdict = gate().evaluate({
        "sources": ["scraped_marketplace"], "data_types": ["company_public_data"]})
    assert verdict["requires_review"] is True
    assert verdict["source_policy"] == "needs_review"


def test_unknown_data_type_default_deny():
    verdict = gate().evaluate({"sources": ["search_api"], "data_types": ["biometric_data"]})
    assert verdict["requires_review"] is True
