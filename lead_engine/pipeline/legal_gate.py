"""Legal Gate — a policy engine, not a lawyer.

Evaluates records against config/legal_policies/<country>.yaml:
source type, data type, retention, purpose. Default-deny: anything not
explicitly defined is flagged requires_review. The actual policies depend
on country, source, collection method and each provider's ToS.
"""
from datetime import datetime, timedelta, timezone


class LegalGate:
    def __init__(self, policy: dict):
        self.policy = policy or {}

    def evaluate(self, lead: dict) -> dict:
        data_types = lead.get("data_types") or self._infer_types(lead)
        rules = self.policy.get("data_types", {}) or {}

        storage_allowed = True
        requires_review = False
        retentions = []
        for dt in data_types:
            rule = rules.get(dt)
            if rule is None:            # default-deny on unknown data types
                requires_review = True
                continue
            if rule.get("storage_allowed") is False:
                storage_allowed = False
            if rule.get("requires_review"):
                requires_review = True
            if rule.get("retention_days") is not None:
                retentions.append(int(rule["retention_days"]))

        src_rules = self.policy.get("source_types", {}) or {}
        approved = True
        for source in lead.get("sources") or []:
            rule = src_rules.get(source)
            if rule is None or not rule.get("approved", False):
                approved = False
                requires_review = True

        purpose = lead.get("purpose", "lead_generation")
        purpose_rule = (self.policy.get("purposes", {}) or {}).get(purpose)
        if purpose_rule is None:
            requires_review = True

        retention = min(retentions) if retentions else int(
            self.policy.get("default_retention_days", 30))
        expires_at = (
            datetime.now(timezone.utc) + timedelta(days=retention)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        decision = "REJECTED" if not storage_allowed else (
            "REVIEW" if requires_review else "ACCEPTED")
        return {
            "storage_allowed": storage_allowed,
            "requires_review": requires_review,
            "purpose": purpose_rule or "needs_review",
            "retention_days": retention,
            "expires_at": expires_at,
            "source_policy": "approved" if approved else "needs_review",
            "decision": decision,
        }

    @staticmethod
    def _infer_types(lead: dict):
        types = ["company_public_data"]
        if lead.get("email") or lead.get("phone"):
            types.append("professional_contact")
        return types
