"""One worker tick: reclaim expired leases, lease a job, drive it to a
terminal state, flush the event outbox.

Lives here — not in __main__ or the API layer — so the CLI worker loop and
the Vercel cron function execute the same logic. The zombie RUNNING runs in
the gap register (FRONT-03) happened because production never called this
machinery; the cron endpoint closes that gap.

seed_csv is an inline-run affordance only: queue mode enqueues a bare
job_id, so API-started runs that pass seed_csv lose it in queue mode.
"""
import os
import time

from . import queue
from .config import load_settings


def tick_budget_seconds() -> float:
    """Wall-clock a serverless tick may spend driving a job. Vercel kills the
    function at maxDuration (60 s) with a 504, so the default leaves headroom
    for finalize writes and the response. 0/invalid disables slicing (CLI)."""
    try:
        return float(os.environ.get("LEAD_ENGINE_TICK_BUDGET_SECONDS", "45"))
    except ValueError:
        return 45.0


def run_worker_tick(db, worker_id: str, settings: dict | None = None,
                    lease_seconds: int = 600,
                    budget_seconds: float | None = None) -> dict:
    """Run exactly one scheduling step. Returns what happened, never raises:
    the cron endpoint reports this dict over HTTP instead of a stack trace."""
    started = time.monotonic()
    budget = tick_budget_seconds() if budget_seconds is None else budget_seconds
    result = {"worker_id": worker_id, "reclaimed": 0, "stale_runs_reaped": 0,
              "paused_expired": 0, "woken": 0, "retention_erased": 0,
              "leased": False, "job_id": None,
              "state": None, "error": None, "yielded": False}
    result["reclaimed"] = queue.reclaim_expired(db)
    result["paused_expired"] = queue.expire_stale_paused(db)
    result["woken"] = queue.wake_due_paused(db)
    try:
        from .agent_registry import reclaim_stale_runs

        result["stale_runs_reaped"] = reclaim_stale_runs(db)
    except Exception:
        pass  # reaping must never break the tick
    try:
        from .privacy import retain_expired

        result["retention_erased"] = retain_expired(db)
    except Exception:
        result["retention_erased"] = -1  # sweep failure surfaces in the result
    job = queue.lease_next(db, worker_id, lease_seconds)
    if not job:
        return result
    result["leased"] = True
    result["job_id"] = job["job_id"]
    try:
        from .research import ResearchJobManager

        if ResearchJobManager(db).is_research(job["job_id"]):
            # agentic research path — resumable, budgeted, human gate
            from .research.orchestrator import ResearchOrchestrator

            kwargs = {"deadline": started + budget} if budget > 0 else {}
            summary = ResearchOrchestrator(
                db, settings or load_settings(), job["job_id"], **kwargs).run()
            state = summary.get("state") or "READY_FOR_REVIEW"
            if summary.get("yielded"):
                # ran out of request time, not out of work: back to the queue
                # with the attempt refunded; the next tick resumes (E3)
                queue.yield_slice(db, job["job_id"])
                result["yielded"] = True
            elif state == "PAUSED":
                queue.fail(db, job["job_id"],
                           summary.get("pause_reason") or "paused")
            else:
                # READY_FOR_REVIEW / WAITING_FOR_USER / CANCELLED:
                # the state belongs to the human gate now, not the queue
                queue.release(db, job["job_id"])
        else:
            from .benchmark.run import run_benchmark
            from .config import load_icp

            summary, _metrics, _outputs = run_benchmark(
                load_icp(job["icp_id"]), job_id=job["job_id"])
            state = summary.get("state") or "COMPLETED"
            if state == "PAUSED":
                queue.fail(db, job["job_id"],
                           summary.get("pause_reason") or "paused")
            else:
                queue.complete(db, job["job_id"])
            _dispatch(db)
        result["state"] = state
    except Exception as exc:
        reason = f"{type(exc).__name__}: {exc}"
        result["state"] = queue.fail(db, job["job_id"], reason)
        result["error"] = reason
        try:
            from .events import emit

            emit(db, os.environ.get("LEAD_ENGINE_ORG_ID"), "job.failed",
                 "job", job["job_id"], {"job_id": job["job_id"],
                                        "error": reason})
        except Exception:
            pass
        _dispatch(db)
    return result


def _dispatch(db) -> None:
    """Flush outbox: send webhooks/notifications without a separate
    event-worker process (serverless-safe)."""
    try:
        from .events import dispatch_pending

        dispatch_pending(db)
    except Exception:
        pass
