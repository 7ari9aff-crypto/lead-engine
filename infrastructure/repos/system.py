"""System-plane ports implementations: bootstrap, plans, job runtime.

These wrap runtime/leasing (durable jobs) and platform bootstrap SQL. They are
the concrete adapters the composition root (api/apps) wires into use cases.
"""
from __future__ import annotations

from typing import Any

from runtime import leasing


class BootstrapPg:
    def __init__(self, db):
        self._db = db

    def plan_exists(self, plan_code: str) -> bool:
        with self._db.tx_system() as conn, conn.cursor() as cur:
            return cur.execute("SELECT 1 FROM platform.plans WHERE code = %s",
                               (plan_code,)).fetchone() is not None

    def create_org(self, org_id: str, slug: str, name: str, plan_code: str,
                   owner_ext_id: str) -> str:
        with self._db.tx(org_id) as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO platform.organizations (id, slug, name, plan_code)
                   VALUES (%s, %s, %s, %s)""",
                (org_id, slug, name, plan_code),
            )
            cur.execute(
                "INSERT INTO platform.members (org_id, user_ext_id, role) VALUES (%s, %s, %s)",
                (org_id, owner_ext_id, "owner"),
            )
        return org_id


class PlansReaderPg:
    def __init__(self, db):
        self._db = db

    def plan_for_org(self, org_id: str) -> dict[str, Any]:
        # Self-scoped read: tenant set to the org itself so FORCE RLS passes.
        with self._db.tx(org_id) as conn, conn.cursor() as cur:
            row = cur.execute(
                """SELECT o.plan_code, p.limits FROM platform.organizations o
                   JOIN platform.plans p ON p.code = o.plan_code WHERE o.id = %s""",
                (org_id,),
            ).fetchone()
        return dict(row) if row else {}


class JobRuntimePg:
    def __init__(self, db):
        self._db = db

    def enqueue(self, org_id: str, job_type: str, payload: dict[str, Any],
                queue: str = "default", campaign_id: str | None = None) -> str:
        return leasing.create_job(self._db, org_id, job_type, payload,
                                  queue=queue, campaign_id=campaign_id)

    def active_count(self, org_id: str) -> int:
        return leasing.active_job_count(self._db, org_id)

    def get(self, org_id: str, job_id: str) -> dict[str, Any] | None:
        return leasing.get_job(self._db, org_id, job_id)

    def list(self, org_id: str, limit: int = 50) -> list[dict[str, Any]]:
        return leasing.list_jobs(self._db, org_id, limit)

    def events(self, job_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._db.tx_system() as conn, conn.cursor() as cur:
            return list(cur.execute(
                """SELECT kind, data, created_at FROM runtime.job_events
                   WHERE job_id = %s ORDER BY id DESC LIMIT %s""",
                (job_id, limit),
            ).fetchall())

    def cancel(self, org_id: str, job_id: str, cancelled_by: str, reason: str) -> bool:
        return leasing.request_cancel(self._db, org_id, job_id, cancelled_by, reason)

    def resume(self, org_id: str, job_id: str) -> bool:
        return leasing.resume_job(self._db, org_id, job_id)
