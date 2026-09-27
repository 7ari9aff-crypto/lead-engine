"""Worker engine: claim → run handler (with job ops) → complete/fail.

The same engine powers every worker subscription; the difference is only the
queues it serves (architecture §38). Handlers receive JobOps — the fenced
runtime surface (checkpoint/phase/heartbeat/cancel) — and a UnitOfWork factory
for business work.
"""
from __future__ import annotations

import time
from typing import Any, Callable

from contracts.errors import LeaseLostError
from infrastructure.config import Settings
from application.ports import JobContext
from runtime import leasing


class JobOps:
    """Fenced runtime surface handed to handlers for the current attempt."""

    def __init__(self, db, settings: Settings, ctx: JobContext, uow_factory=None,
                 gateway=None, model_gateway=None):
        self._db = db
        self._settings = settings
        self.ctx = ctx
        self._uow_factory = uow_factory
        self.gateway = gateway
        self.model_gateway = model_gateway

    # -- fenced progress -----------------------------------------------------
    def checkpoint(self, data: dict[str, Any], state: str | None = None) -> None:
        leasing.save_checkpoint(self._db, self.ctx.job_id, self.ctx.lease_token,
                                self.ctx.lease_version, data, state=state,
                                lease_seconds=self._settings.lease_seconds)
        self.ctx.checkpoint = data

    def set_phase(self, state: str) -> None:
        leasing.set_phase(self._db, self.ctx.job_id, self.ctx.lease_token,
                          self.ctx.lease_version, state,
                          lease_seconds=self._settings.lease_seconds)

    def heartbeat(self) -> bool:
        return leasing.heartbeat(self._db, self.ctx.job_id, self.ctx.lease_token,
                                 self._settings.lease_seconds)

    # -- cancellation ----------------------------------------------------------
    def cancel_requested(self) -> bool:
        row = leasing.get_job(self._db, self.ctx.org_id, self.ctx.job_id)
        return bool(row and row["cancel_requested_at"])

    def finish_cancelled(self) -> None:
        leasing.finish_cancelled(self._db, self.ctx.job_id, self.ctx.lease_token,
                                 self.ctx.lease_version)

    def apply_cancellation(self) -> bool:
        return leasing.apply_cancellation(self._db, self.ctx.job_id,
                                          self.ctx.lease_token, self.ctx.lease_version)

    # -- business work -----------------------------------------------------------
    def uow(self):
        assert self._uow_factory is not None, "worker has no uow factory"
        return self._uow_factory(self.ctx.org_id, job=self.ctx)


Handler = Callable[[JobContext, JobOps], str]


class Worker:
    """One binary, many subscriptions. run_once returns True when it did work."""

    def __init__(self, db, settings: Settings, handlers: dict[str, Handler],
                 queues: list[str], worker_id: str, gateway=None, model_gateway=None,
                 relay=None, uow_factory=None):
        self._db = db
        self._settings = settings
        self._handlers = handlers
        self._queues = queues
        self._worker_id = worker_id
        self._gateway = gateway
        self._model_gateway = model_gateway
        self._relay = relay
        self._uow_factory = uow_factory

    def run_maintenance(self) -> dict[str, int]:
        """Reaper + relay tick + effect reconciliation — all idempotent."""
        requeued = leasing.reclaim_expired(self._db)
        dispatched = self._relay.tick() if self._relay else 0
        flagged = self._reconcile_uncertain_effects()
        return {"requeued": len(requeued), "dispatched": dispatched,
                "reconciliation_flags": flagged}

    def _reconcile_uncertain_effects(self) -> int:
        """Effects stuck in 'uncertain' for over a day get a durable human
        review item (§15: ambiguity → reconciliation, never blind retry)."""
        with self._db.tx_system() as conn, conn.cursor() as cur:
            rows = cur.execute(
                """SELECT id, org_id FROM effects.effect_ledger
                   WHERE status = 'uncertain'
                     AND created_at < now() - interval '24 hours'
                     AND reconciled_at IS NULL
                   LIMIT 20""").fetchall()
            flagged = 0
            for row in rows:
                exists = cur.execute(
                    """SELECT 1 FROM agents.approvals
                       WHERE subject_type = 'effect' AND subject_id = %s
                         AND status = 'pending' LIMIT 1""",
                    (str(row["id"]),),
                ).fetchone()
                if exists:
                    continue
                cur.execute(
                    """INSERT INTO agents.approvals
                         (org_id, subject_type, subject_id, action, status,
                          requested_by)
                       VALUES (%s, 'effect', %s, 'reconcile_effect', 'pending',
                               'reconciliation-worker')""",
                    (str(row["org_id"]), str(row["id"])),
                )
                cur.execute(
                    "UPDATE effects.effect_ledger SET reconciled_at = now() WHERE id = %s",
                    (row["id"],),
                )
                flagged += 1
        return flagged

    def run_once(self) -> bool:
        self.run_maintenance()
        job = leasing.claim_next(self._db, self._queues, self._worker_id,
                                 self._settings.lease_seconds)
        if job is None:
            return False

        ctx = JobContext(
            job_id=str(job["id"]),
            org_id=str(job["org_id"]),
            campaign_id=str(job["campaign_id"]) if job["campaign_id"] else None,
            job_type=job["job_type"],
            payload=job["payload"] or {},
            checkpoint=job["checkpoint"] or {},
            lease_token=str(job["lease_token"]),
            lease_version=int(job["lease_version"]),
            worker_id=self._worker_id,
        )
        ops = JobOps(self._db, self._settings, ctx, uow_factory=self._uow_factory,
                     gateway=self._gateway, model_gateway=self._model_gateway)

        handler = self._handlers.get(job["job_type"])
        if handler is None:
            leasing.fail(self._db, ctx.job_id, ctx.lease_token, ctx.lease_version,
                         f"no handler for job_type {job['job_type']}")
            return True

        try:
            terminal_state = handler(ctx, ops)
            leasing.complete(self._db, ctx.job_id, ctx.lease_token, ctx.lease_version,
                             terminal_state)
        except LeaseLostError:
            pass  # a newer attempt owns the job — stop quietly
        except Exception as exc:  # noqa: BLE001 — failures must be recorded
            try:
                leasing.fail(self._db, ctx.job_id, ctx.lease_token, ctx.lease_version,
                             f"{type(exc).__name__}: {exc}")
            except LeaseLostError:
                pass
        return True

    def run(self, max_cycles: int | None = None) -> None:
        cycles = 0
        while max_cycles is None or cycles < max_cycles:
            did_work = self.run_once()
            cycles += 1
            if not did_work:
                time.sleep(self._settings.worker_poll_seconds)
