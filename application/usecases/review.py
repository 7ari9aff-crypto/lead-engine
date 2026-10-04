"""Review use case: the human approval boundary (architecture §31).

The Research Core ends at READY_FOR_REVIEW. Only a human decision (recorded
durably + audited + evented) can move a lead forward. There is no path from
'AI says yes' to outbound execution.
"""
from __future__ import annotations

from application.ports import UowFactory
from contracts.events import LEAD_APPROVED, LEAD_REJECTED, EventEnvelope
from contracts.errors import NotFoundError, PolicyBlocked
from domain.governance.policy import FAIL_CLOSED_VERSION
from domain.governance.policy import GovernanceDecision, PolicyInput, evaluate, fail_closed


class ReviewUseCase:
    def __init__(self, uows: UowFactory):
        self._uows = uows

    def pending(self, org_id: str, limit: int = 50) -> list[dict]:
        with self._uows(org_id) as tx:
            return tx.repos.projects.list_leads(state="READY_FOR_REVIEW", limit=limit)

    def decide(self, org_id: str, lead_id: str, actor: str, approve: bool,
               reason: str = "") -> dict:
        refusal = None
        result: dict = {}
        with self._uows(org_id) as tx:
            lead = tx.repos.projects.get_lead(lead_id)
            if lead is None:
                raise NotFoundError("lead not found (or belongs to another tenant)")

            subject_value = (lead.get("display") or {}).get("domain")
            policy = tx.repos.governance.get_active_policy()
            if policy is None:
                # FAIL CLOSED: an org without an adopted policy cannot approve
                # outreach. The refusal is recorded and COMMITTED — raising
                # inside this block would roll the audit row back.
                decision, basis, why = fail_closed(
                    PolicyInput(operation="lead.outreach",
                                subject_kind="domain", subject_value=subject_value))
                tx.repos.governance.record_decision(
                    "lead", lead_id, "lead.outreach", decision.value,
                    FAIL_CLOSED_VERSION, basis, why, actor,
                )
                refusal = f"policy fail-closed: {why}"
            else:
                decision, basis, why = evaluate(
                    policy["rules"], PolicyInput(
                        operation="lead.outreach",
                        subject_kind="domain", subject_value=subject_value),
                )
                tx.repos.governance.record_decision(
                    "lead", lead_id, "lead.outreach", decision.value,
                    policy["version"], basis, why, actor,
                )
                if approve and decision is GovernanceDecision.BLOCKED:
                    refusal = f"policy blocks outreach for this lead: {why}"
                else:
                    new_state = "APPROVED" if approve else "REJECTED"
                    if not tx.repos.projects.decide_lead(lead_id, new_state, actor):
                        raise NotFoundError("lead is not awaiting review")
                    tx.emit(EventEnvelope(
                        type=LEAD_APPROVED if approve else LEAD_REJECTED,
                        aggregate_type="lead", aggregate_id=lead_id, org_id=org_id,
                        payload={"decided_by": actor, "reason": reason,
                                 "policy": decision.value,
                                 "policy_version": policy["version"]},
                    ))
                    result = {"lead_id": lead_id, "state": new_state,
                              "policy": decision.value,
                              "policy_version": policy["version"]}
        if refusal:
            raise PolicyBlocked(refusal)
        return result
