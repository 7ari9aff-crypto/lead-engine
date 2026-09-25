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

from . import queue
from .config import load_settings


def run_worker_tick(db, worker_id: str, settings: dict | None = None,
                    lease_seconds: int = 600) -> dict:
    """Run exactly one scheduling step. Returns what happened, never raises:
    the cron endpoint reports this dict over HTTP instead of a stack trace."""
    result = {"worker_id": worker_id, "reclaimed": 0, "stale_runs_reaped": 0,
              "retention_erased": 0, "leased": False, "job_id": None,
              "state": None, "error": None}
    result["reclaimed"] = queue.reclaim_expired(db)
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

            summary = ResearchOrchestrator(
                db, settings or load_settings(), job["job_id"]).run()
            state = summary.get("state") or "READY_FOR_REVIEW"
            if state == "PAUSED":
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
