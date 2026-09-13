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

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..db import open_db, utcnow
from ..research import ResearchJobManager

router = APIRouter(prefix="/api/v1/research", tags=["research"])


def get_db(request: Request = None):
    db = open_db()
    try:
        if request is not None:
            claims = getattr(request.state, "claims", None)
            if claims:
                from .. import auth_jwt

                resolved = auth_jwt.resolve_org_id(claims, db)
                if resolved:
                    db.org_id = resolved
        yield db
    finally:
        db.conn.close()


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
    import os

    allowed, reason = check_job_start(db, os.environ.get("LEAD_ENGINE_ORG_ID"))
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
async def research_stream(job_id: str, request: Request, db=Depends(get_db)):
    """Real-time SSE progress stream for the UI/chat (directive §39 / docs/handoff).
    Streams state transitions and counter updates without client polling."""
    _owned(db, job_id)

    async def event_generator():
        last_updated = None
        manager = ResearchJobManager(db)
        terminal_states = {"COMPLETED", "FAILED", "CANCELLED", "READY_FOR_REVIEW", "WAITING_FOR_USER"}
        for _ in range(360):
            if await request.is_disconnected():
                break
            prog = manager.progress(job_id)
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

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
