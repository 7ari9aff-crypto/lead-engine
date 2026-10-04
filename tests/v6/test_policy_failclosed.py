"""Governance fail-closed: an org with NO adopted policy must never get an
ALLOWED verdict — the gate refuses, records the refusal under the fail-closed
version, and the caller surfaces PolicyBlocked/DomainError."""
from __future__ import annotations

import uuid

import pytest

from application.usecases.review import ReviewUseCase
from contracts.errors import PolicyBlocked


def _insert_lead(uows, org: str) -> str:
    with uows(org) as tx:
        company_id = str(uuid.uuid4())
        tx.repos.companies.create_company(company_id, "Clinic", "clinic.example",
                                          None, None, None)
        return tx.repos.projects.upsert_lead(
            campaign_id=None, company_id=company_id,
            contact_id=None, icp_version_id=None,
            display={"name": "Clinic", "domain": "clinic.example"},
            masked_email=None, masked_phone=None, email_status=None,
            score=50.0, score_version="v1", decision="review")


def test_review_fails_closed_without_policy(org, uows):
    """Delete the org's only policy version → review.decide must refuse."""
    lead_id = _insert_lead(uows, org)

    with uows(org) as tx:
        assert tx.repos.governance.get_active_policy() is not None

    with uows(org) as tx:
        tx.cursor.execute(
            "DELETE FROM governance.legal_policy_versions WHERE org_id = %s", (org,))

    with pytest.raises(PolicyBlocked):
        ReviewUseCase(uows).decide(org, lead_id, "owner-1", approve=True)

    with uows(org) as tx:
        rows = tx.cursor.execute(
            """SELECT policy_version, decision FROM governance.legal_decisions
               WHERE org_id = %s AND subject_id = %s
               ORDER BY created_at DESC LIMIT 1""", (org, lead_id)).fetchall()
    assert rows, "the refusal itself must be recorded"
    assert rows[0]["policy_version"] == "fail-closed"
    assert rows[0]["decision"] == "BLOCKED"
