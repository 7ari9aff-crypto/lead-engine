"""Event envelope (architecture §32). Versioned; PII-free by contract.

Every event crossing context boundaries is serialized into this envelope and
stored in events.outbox inside the same transaction as the mutation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class EventEnvelope:
    type: str
    aggregate_type: str
    aggregate_id: str
    org_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    version: int = 1
    producer: str = "lead-engine-v6"
    event_id: str = field(default_factory=lambda: str(uuid4()))
    trace_id: str | None = None
    correlation_id: str | None = None
    causation_id: str | None = None

    def to_row(self) -> dict[str, Any]:
        data = asdict(self)
        data["payload"] = serialize(self.payload)
        return data


def serialize(value: Any) -> Any:
    """Make payloads JSON-safe (uuids/dates become strings)."""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [serialize(v) for v in value]
    if isinstance(value, dict):
        return {k: serialize(v) for k, v in value.items()}
    return value


# Canonical event types (breaking changes = new version suffix in payload type registry)
LEAD_READY_FOR_REVIEW = "acquisition.lead.ready_for_review"
LEAD_APPROVED = "acquisition.lead.approved"
LEAD_REJECTED = "acquisition.lead.rejected"
CAMPAIGN_STATE_CHANGED = "acquisition.campaign.state_changed"
VERIFICATION_COMPLETED = "intelligence.verification.completed"
POLICY_DECISION_RECORDED = "governance.decision.recorded"
