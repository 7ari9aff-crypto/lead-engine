"""Agent boundary rules (pure). The agent proposes; it never owns truth.

Research agents are capability-limited: no outreach, no raw PII, no direct
state mutation. Outreach capability lives exclusively in the (future) Revenue
Execution plugin with its own agent, broker, budget and audit.
"""
from __future__ import annotations

from enum import StrEnum


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AgentType(StrEnum):
    RESEARCH = "research"
    OUTREACH = "outreach"      # exists only inside the Revenue Execution plugin


# Tools a research agent may never call — enforced by the Tool Broker.
FORBIDDEN_FOR_RESEARCH = frozenset({
    "send_email", "send_whatsapp", "send_linkedin", "create_sequence",
    "outreach_send", "direct_sql", "read_pii_plaintext", "rotate_keys",
})


def assert_tool_allowed(agent_type: AgentType, tool_id: str) -> None:
    if agent_type is AgentType.RESEARCH and tool_id in FORBIDDEN_FOR_RESEARCH:
        raise PermissionError(f"tool {tool_id} is forbidden for {agent_type.value} agents")


def required_approval(risk_level: RiskLevel, policy_decision: str) -> bool:
    """High-risk actions always require a durable human approval; policy may
    demand one for medium-risk actions too."""
    if risk_level is RiskLevel.HIGH:
        return True
    if risk_level is RiskLevel.MEDIUM and policy_decision == "NEEDS_REVIEW":
        return True
    return False
