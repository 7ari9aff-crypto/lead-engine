"""Review use case: the human approval boundary (architecture §31).

The Research Core ends at READY_FOR_REVIEW. Only a human decision (recorded
durably + audited + evented) can move a lead forward. There is no path from
'AI says yes' to outbound execution.
"""
from __future__ import annotations

from application.ports import UowFactory
from contracts.events import LEAD_APPROVED, LEAD_REJECTED, EventEnvelope
from contracts.errors import NotFoundError, PolicyBlocked
from domain.governance.policy import VERSION as POLICY_VERSION
from domain.governance.policy import GovernanceDecision, PolicyInput, default_rules, evaluate


class ReviewUseCase:
    def __init__(self, uows: UowFactory):
        self._uows = uows

    def pending(self, org_id: str, limit: int = 50) -> list[dict]:
        with self._uows(org_id) as tx:
            return tx.repos.projects.list_leads(state="READY_FOR_REVIEW", limit=limit)

    def decide(self, org_id: str, lead_id: str, actor: str, approve: bool,
               reason: str = "") -> dict:
        with self._uows(org_id) as tx:
            lead = tx.repos.projects.get_lead(lead_id)
            if lead is None:
                raise NotFoundError("lead not found (or belongs to another tenant)")

            rules = tx.repos.governance.get_policy_rules() or default_rules()
            decision, basis, why = evaluate(
                rules, PolicyInput(operation="lead.outreach",
                                   subject_kind="domain",
                                   subject_value=(lead.get("display") or {}).get("domain")),
            )
            tx.repos.governance.record_decision(
                "lead", lead_id, "lead.outreach", decision.value, POLICY_VERSION,
                basis, why, actor,
            )
            if approve and decision is GovernanceDecision.BLOCKED:
                raise PolicyBlocked(f"policy blocks outreach for this lead: {why}")

            new_state = "APPROVED" if approve else "REJECTED"
            if not tx.repos.projects.decide_lead(lead_id, new_state, actor):
                raise NotFoundError("lead is not awaiting review")

            tx.emit(EventEnvelope(
                type=LEAD_APPROVED if approve else LEAD_REJECTED,
                aggregate_type="lead", aggregate_id=lead_id, org_id=org_id,
                payload={"decided_by": actor, "reason": reason,
                         "policy": decision.value},
            ))
            return {"lead_id": lead_id, "state": new_state, "policy": decision.value}
