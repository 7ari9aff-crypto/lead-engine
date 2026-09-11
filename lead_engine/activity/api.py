"""HTTP surface for the activity feed — FastAPI router.

Endpoints:
  GET  /api/activity?limit=50&kind=job.started
  POST /api/activity  {kind, payload, correlation_id?}

The dashboard polls GET every 5s. POST is for in-process emitters that want
to log to the feed directly (most emitters go through observability/* which
can fan out to this store).
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..db import open_db
from .store import ActivityStore

router = APIRouter(tags=["activity"])


class ActivityRecordRequest(BaseModel):
    kind: str
    payload: dict = {}
    correlation_id: str | None = None


def get_db():
    """Local DI — same connection style as lead_engine/api/app.py:get_db.

    Keeping the dependency local avoids a circular import with app.py while
    still letting FastAPI inject a fresh per-request Database handle."""
    db = open_db()
    try:
        yield db
    finally:
        db.conn.close()


def get_store(db = Depends(get_db)) -> ActivityStore:
    return ActivityStore(db)


@router.get("/api/activity")
def list_activity(
    limit: int = 50,
    kind: str | None = None,
    store: ActivityStore = Depends(get_store),
):
    if limit > 200:
        limit = 200
    if limit < 1:
        limit = 1
    return {"events": store.list(limit=limit, kind=kind)}


@router.post("/api/activity")
def record_activity(req: ActivityRecordRequest,
                    store: ActivityStore = Depends(get_store)):
    if not req.kind or not isinstance(req.kind, str):
        raise HTTPException(status_code=422, detail="kind is required")
    event = store.record(req.kind, req.payload or {}, correlation_id=req.correlation_id)
    return {"event": event}


def get_router():
    """Convenience for mounting in app.py — keeps the import surface small."""
    return router
