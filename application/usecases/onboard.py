"""Onboarding: create an organization with an owner member.

Org creation is a system-plane operation (the tenant exists only after the
insert), implemented by the BootstrapPort. The INSERT runs under
app.tenant_id = the new id so FORCE RLS WITH CHECK passes.
"""
from __future__ import annotations

from uuid import uuid4

from application.ports import BootstrapPort
from contracts.errors import DomainError


class OnboardOrg:
    def __init__(self, bootstrap: BootstrapPort):
        self._bootstrap = bootstrap

    def execute(self, slug: str, name: str, plan_code: str, owner_ext_id: str) -> dict:
        if not self._bootstrap.plan_exists(plan_code):
            raise DomainError(f"unknown plan {plan_code}")
        org_id = str(uuid4())
        self._bootstrap.create_org(org_id, slug, name, plan_code, owner_ext_id)
        return {"org_id": org_id, "slug": slug, "plan": plan_code}
