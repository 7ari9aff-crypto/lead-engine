"""HTTP surface for the activity feed — FastAPI router.

Endpoints:
  GET  /api/activity?limit=50&kind=job.started
  POST /api/activity  {kind, payload, correlation_id?}
  GET  /api/audit?limit=50&offset=0&actor=&action=&entity_type=&entity_id=
                   &from=&to=&before_id=

The dashboard polls GET /api/activity every 5s. POST is for in-process emitters
that want to log to the feed directly (most emitters go through observability/*
which can fan out to this store).

GET /api/audit is the read path over the server-side `audit_logs` provenance
table (written by db.audit() / codeops.audit()). Tenant-scoped, newest-first,
one SELECT per page. See AuditTrailStore in store.py for the visibility rules.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from .store import ActivityStore, AuditTrailStore

router = APIRouter(tags=["activity"])


class ActivityRecordRequest(BaseModel):
    kind: str
    payload: dict = {}
    correlation_id: str | None = None


# Tenant resolution is unified in lead_engine.tenant (claims first;
# fail-closed for users with no membership; env bridge for machine contexts).
from ..tenant import db_handle as get_db


def get_store(db = Depends(get_db)) -> ActivityStore:
    return ActivityStore(db)


def get_audit_store(db = Depends(get_db)) -> AuditTrailStore:
    return AuditTrailStore(db)


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


@router.get("/api/audit")
def list_audit(
    limit: int = 50,
    offset: int = 0,
    actor: str | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    since: str | None = Query(None, alias="from"),
    until: str | None = Query(None, alias="to"),
    before_id: int | None = None,
    store: AuditTrailStore = Depends(get_audit_store),
):
    """Server-side audit trail: who did what to which entity, when.

    Newest-first page over audit_logs, scoped to the caller's tenant.
    Pagination: `offset` for random access, `before_id` (echoed back as
    next_before_id) for a stable keyset scroll — created_at is second-
    precision so offset paging alone can duplicate/skip tied rows.
    Filters are ANDed server-side; per-entity provenance is a first-class
    query (?entity_type=lead&entity_id=...), not a client-side filter.
    """
    if before_id is not None and before_id < 0:
        raise HTTPException(status_code=400, detail="before_id must be >= 0")
    try:
        page = store.list(
            limit=limit, offset=offset,
            actor=actor or None, action=action or None,
            entity_type=entity_type or None, entity_id=entity_id or None,
            created_from=since, created_to=until, before_id=before_id,
        )
    except ValueError as exc:  # bad time-window bound
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    entries = page["entries"]
    return {
        "entries": entries,
        "count": len(entries),
        "scope": page["scope"],
        "limit": max(1, min(int(limit), 200)),
        "offset": max(0, int(offset)),
        "next_before_id": entries[-1]["id"] if entries else None,
    }


def get_router():
    """Convenience for mounting in app.py — keeps the import surface small."""
    return router
