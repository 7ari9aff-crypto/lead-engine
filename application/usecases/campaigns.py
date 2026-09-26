"""Campaign use cases: create (with entitlement enforcement before enqueue)
and durable job queries — through ports only."""
from __future__ import annotations

from typing import Any

from application.ports import JobRuntime, PlansReader, UowFactory
from contracts.errors import EntitlementExceeded, NotFoundError


class CreateCampaign:
    """ICP version (immutable) + campaign + QUEUED acquisition job.

    Entitlements are enforced BEFORE the job row exists — the legacy bug of
    checking after creation (or not at all) is structurally impossible here.
    """

    def __init__(self, uows: UowFactory, plans: PlansReader, jobs: JobRuntime):
        self._uows = uows
        self._plans = plans
        self._jobs = jobs

    def execute(self, org_id: str, name: str, icp_definition: dict[str, Any],
                budget_cents: int = 0) -> dict[str, Any]:
        plan = self._plans.plan_for_org(org_id)
        if not plan:
            raise NotFoundError("organization not found")
        limits = plan.get("limits") or {}
        max_jobs = int(limits.get("max_concurrent_jobs", 1))
        active = self._jobs.active_count(org_id)
        if active >= max_jobs:
            raise EntitlementExceeded(
                f"plan {plan.get('plan_code')} allows {max_jobs} concurrent job(s); "
                f"{active} active"
            )

        with self._uows(org_id) as tx:
            icp_version_id = tx.repos.acquisition.create_icp_version(
                profile_name=str(icp_definition.get("name", "default")),
                definition=icp_definition,
            )
            campaign_id = tx.repos.acquisition.create_campaign(name, icp_version_id,
                                                               budget_cents)
        job_id = self._jobs.enqueue(
            org_id, job_type="acquisition.run",
            payload={"campaign_id": campaign_id, "icp_version_id": icp_version_id,
                     "budget_cents": budget_cents},
            campaign_id=campaign_id,
        )
        return {"campaign_id": campaign_id, "icp_version_id": icp_version_id,
                "job_id": job_id}


class JobQuery:
    def __init__(self, jobs: JobRuntime):
        self._jobs = jobs

    def get(self, org_id: str, job_id: str) -> dict[str, Any]:
        job = self._jobs.get(org_id, job_id)
        if job is None:
            raise NotFoundError("job not found")
        return {"job": job, "events": self._jobs.events(job_id)}

    def list(self, org_id: str, limit: int = 50) -> list[dict[str, Any]]:
        return self._jobs.list(org_id, limit)

    def cancel(self, org_id: str, job_id: str, cancelled_by: str, reason: str) -> bool:
        return self._jobs.cancel(org_id, job_id, cancelled_by, reason)

    def resume(self, org_id: str, job_id: str) -> bool:
        return self._jobs.resume(org_id, job_id)
