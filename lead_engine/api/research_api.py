import asyncio
from fastapi.responses import StreamingResponse
"""Research job API — the chat-first entry point (directive §32).

POST /api/v1/research           create a research job (QUEUED); inline mode
                                runs it in the background, platform mode
                                enqueues for the worker fleet
GET  /api/v1/research/{job_id}  live progress: state, counters, budgets,
                                stats, stop_reason — this is what the chat
                                narrates and the UI polls
POST /api/v1/research/{job_id}/cancel    user stop (terminal)
POST /api/v1/research/{job_id}/answer    answer an open question -> job
                                returns to RUNNING (WAITING_FOR_USER exit)
POST /api/v1/research/{job_id}/resume    RESEARCH_MORE from READY_FOR_REVIEW
                                or capacity-resume for PAUSED
GET  /api/v1/research/{job_id}/events    narration trail (job_events)
"""
import json
import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..db import open_db, utcnow
from ..research import ResearchJobManager

router = APIRouter(prefix="/api/v1/research", tags=["research"])


# Tenant resolution is unified in lead_engine.tenant (claims first;
# fail-closed for users with no membership; env bridge for machine contexts).
from ..tenant import db_handle as get_db


class ResearchRequest(BaseModel):
    objective: str = Field(..., min_length=3)
    icp_version_id: str | None = None
    budgets: dict | None = None
    parent_job_id: str | None = None


class AnswerRequest(BaseModel):
    answer: str = Field(..., min_length=1)


def _owned(db, job_id: str):
    """404 for other tenants' jobs — never 403 (existence is not disclosed).
    PG enforces this with FORCED RLS; SQLite (dev) gets the explicit check."""
    ctx = ResearchJobManager(db).context(job_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="research job not found")
    if getattr(db, "dialect", "sqlite") == "sqlite":
        if ctx.get("organization_id") != (getattr(db, "org_id", None) or "shared"):
            raise HTTPException(status_code=404, detail="research job not found")
    return ctx


@router.post("")
def create_research(req: ResearchRequest, background: BackgroundTasks,
                    db=Depends(get_db)):
    from ..config import load_settings
    from ..queue import enqueue, platform_mode

    manager = ResearchJobManager(db, load_settings())
    job_id = manager.create(req.objective, icp_version_id=req.icp_version_id,
                            budgets=req.budgets, parent_job_id=req.parent_job_id)
    from ..entitlements import check_job_start

    org = getattr(db, "org_id", None)
    if org and not str(org).startswith("__"):
        allowed, reason = check_job_start(db, org)
        if not allowed:
            raise HTTPException(status_code=429, detail=reason)
    if platform_mode():
        enqueue(db, job_id)
    else:
        background.add_task(_run_research, job_id)
    return {"job_id": job_id, "state": "QUEUED",
            "mode": "queue" if platform_mode() else "inline"}


def _run_research(job_id: str):
    from ..config import load_settings
    from ..research.orchestrator import ResearchOrchestrator

    db = open_db()
    try:
        ResearchOrchestrator(db, load_settings(), job_id).run()
    except Exception as exc:  # never hang the caller: record and stop
        from ..jobs import JobManager

        JobManager(db).mark_failed(job_id, f"{type(exc).__name__}: {exc}")
    finally:
        db.conn.close()


@router.get("/{job_id}")
def research_progress(job_id: str, db=Depends(get_db)):
    _owned(db, job_id)
    return ResearchJobManager(db).progress(job_id)


@router.get("/{job_id}/events")
def research_events(job_id: str, limit: int = 100, db=Depends(get_db)):
    _owned(db, job_id)
    rows = db.query(
        "SELECT ts, from_state, to_state, reason FROM job_events"
        " WHERE job_id=? ORDER BY id DESC LIMIT ?", (job_id, max(1, min(limit, 500))))
    return {"events": rows}


@router.post("/{job_id}/cancel")
def research_cancel(job_id: str, db=Depends(get_db)):
    _owned(db, job_id)
    manager = ResearchJobManager(db)
    state = manager.jobs.current(job_id)
    if state in ("COMPLETED", "CANCELLED", "FAILED"):
        raise HTTPException(status_code=409, detail=f"job already {state}")
    manager.cancel(job_id)
    return {"ok": True, "state": "CANCELLED"}


@router.post("/{job_id}/answer")
def research_answer(job_id: str, req: AnswerRequest, background: BackgroundTasks,
                    db=Depends(get_db)):
    """User answered an open question: record it, return to RUNNING, resume."""
    _owned(db, job_id)
    manager = ResearchJobManager(db)
    if manager.jobs.current(job_id) != "WAITING_FOR_USER":
        raise HTTPException(status_code=409,
                            detail=f"job is {manager.jobs.current(job_id)}, "
                                   "not WAITING_FOR_USER")
    questions = None
    from ..truth import FactsStore

    store = FactsStore(db)
    open_qs = store.open_questions(job_id)
    if open_qs:
        store.drop_open_question(open_qs[-1]["id"])  # answered in-thread
    db.execute(
        "INSERT INTO job_events (ts, job_id, from_state, to_state, reason)"
        " VALUES (?,?,?,?,?)",
        (utcnow(), job_id, "WAITING_FOR_USER", "RUNNING",
         f"user answered: {req.answer[:300]}"))
    manager.jobs.transition(job_id, "RUNNING")
    from ..queue import enqueue, platform_mode

    if platform_mode():
        enqueue(db, job_id)
    else:
        background.add_task(_run_research, job_id)
    return {"ok": True, "state": "RUNNING"}


@router.post("/{job_id}/resume")
def research_resume(job_id: str, background: BackgroundTasks, db=Depends(get_db)):
    """Two resume paths: PAUSED (capacity back) and READY_FOR_REVIEW
    (RESEARCH_MORE — continues the SAME context, opens a new agent run)."""
    _owned(db, job_id)
    manager = ResearchJobManager(db)
    state = manager.jobs.current(job_id)
    if state == "PAUSED":
        manager.jobs.resume(job_id)
    elif state == "READY_FOR_REVIEW":
        manager.jobs.transition(job_id, "RUNNING", "RESEARCH_MORE")
    else:
        raise HTTPException(status_code=409,
                            detail=f"job is {state}; only PAUSED or "
                                   "READY_FOR_REVIEW resume")
    from ..queue import enqueue, platform_mode

    if platform_mode():
        enqueue(db, job_id)
    else:
        background.add_task(_run_research, job_id)
    return {"ok": True, "state": "RUNNING"}

@router.get("/{job_id}/stream")
async def research_stream(job_id: str, request: Request, db=Depends(get_db),
                          max_seconds: int = 600):
    """Real-time SSE progress stream for the UI/chat (directive §39 / docs/handoff).
    Streams state transitions and counter updates without client polling.
    Bounded by wall clock (max_seconds) — a stuck stream can never hang a
    client forever; UIs simply reconnect.

    Connection hygiene (gap #2): the request-scoped DB handle is released
    before streaming starts; each poll tick opens a short-lived handle.
    Holding one pooled PG connection open for up to 600s per viewer would
    exhaust the pool under modest concurrency. Tests override the `get_db`
    dependency against a temp DB — honour that by reusing the request's own
    handle when it is file-backed SQLite (same path), instead of opening
    the dev-default database.
    """
    ctx = _owned(db, job_id)
    org_id = getattr(db, "org_id", None)
    dialect = getattr(db, "dialect", "sqlite")
    owner_path = getattr(db, "path", None)
    try:
        db.conn.close()
    except Exception:
        pass
    import time as _time

    from ..db import open_db as _open_db

    started = _time.monotonic()

    def _tick_db():
        if owner_path is not None and dialect == "sqlite":
            from ..db import Database as _Database

            tick = _Database(owner_path)
            tick.org_id = org_id
            return tick
        tick = _open_db(org_id=org_id)
        tick.org_id = org_id
        return tick

    async def event_generator():
        last_updated = None
        terminal_states = {"COMPLETED", "FAILED", "CANCELLED", "READY_FOR_REVIEW", "WAITING_FOR_USER"}
        while _time.monotonic() - started < max_seconds:
            if await request.is_disconnected():
                break
            tick = _tick_db()
            try:
                if dialect == "sqlite" and ctx.get("organization_id") != (org_id or "shared"):
                    break
                prog = ResearchJobManager(tick).progress(job_id)
            finally:
                try:
                    tick.conn.close()
                except Exception:
                    pass
            current_updated = prog.get("updated_at")
            if current_updated != last_updated:
                last_updated = current_updated
                data = json.dumps(prog, ensure_ascii=False, default=str)
                yield f"event: progress\ndata: {data}\n\n"
                if prog.get("state") in terminal_states:
                    yield f"event: done\ndata: {json.dumps({'state': prog.get('state')})}\n\n"
                    break
            else:
                yield ": ping\n\n"
            await asyncio.sleep(2)
        yield f"event: done\ndata: {json.dumps({'state': 'stream_closed'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/openmanus/health")
def openmanus_health(db=Depends(get_db)):
    """Proxy the OpenManus runner's health (command-center services board).
    Never raises: an unreachable runtime is a status, not a crash."""
    from ..research import openmanus

    if not openmanus.is_configured():
        return {"reachable": False, "configured": False,
                "note": "OPENMANUS_BASE_URL غير مهيأ"}
    try:
        import requests

        resp = requests.get(f"{openmanus.base_url()}/health",
                            headers={"Authorization":
                                     f"Bearer {os.environ.get('OPENMANUS_TOKEN', '')}"},
                            timeout=4)
        body = resp.json() if resp.status_code == 200 else {}
        return {"reachable": resp.status_code == 200, "configured": True,
                "status_code": resp.status_code, **body}
    except Exception as exc:
        return {"reachable": False, "configured": True,
                "error": f"{type(exc).__name__}"}
