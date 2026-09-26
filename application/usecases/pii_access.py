"""PII access use case: the ONLY way any surface may read plaintext PII.

Purpose-bound, audited (ADR-0006). Outreach plaintext requires the approved
lead state — the human approval boundary is enforced here too.
"""
from __future__ import annotations

from application.ports import UowFactory
from contracts.errors import DomainError, NotFoundError
from infrastructure.pii.vault import PiiVault, TenantVault


class ContactPiiReader:
    def __init__(self, uows: UowFactory, vault: PiiVault):
        self._uows = uows
        self._vault = vault

    def read(self, org_id: str, lead_id: str, purpose: str, actor: str,
             request_id: str | None = None) -> dict:
        if purpose not in ("verification", "outreach", "human_review", "legal_request"):
            raise DomainError(f"unknown pii purpose {purpose!r}")
        tenant_vault = TenantVault(self._vault, org_id)
        if purpose == "outreach":
            with self._uows(org_id) as tx:
                lead = tx.repos.projects.get_lead(lead_id)
                if lead is None:
                    raise NotFoundError("lead not found")
                if lead["state"] != "APPROVED":
                    raise DomainError("outreach plaintext requires an APPROVED lead")

        with self._uows(org_id) as tx:
            lead = tx.repos.projects.get_lead(lead_id)
            if lead is None:
                raise NotFoundError("lead not found")
            contact_id = lead.get("contact_id")
            if not contact_id:
                raise NotFoundError("lead has no contact")
            for c in tx.repos.contacts.list_company_contacts(str(lead["company_id"])):
                if str(c["id"]) != str(contact_id):
                    continue
                out: dict = {"contact_id": str(c["id"]), "name": c.get("name"),
                             "role": c.get("role")}
                if c.get("email_ref"):
                    out["email"] = tenant_vault.decrypt(str(c["email_ref"]), purpose,
                                                        actor, request_id)
                if c.get("phone_ref"):
                    out["phone"] = tenant_vault.decrypt(str(c["phone_ref"]), purpose,
                                                        actor, request_id)
                return out
        raise NotFoundError("contact not found for lead")
