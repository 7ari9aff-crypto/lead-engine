"""ICP API — the user's filtering criteria as a first-class, versioned object.

Stage 2 (filtering) is only real when the USER can define what qualifies:
these endpoints let the dashboard and the chat create, list, and activate
ICP versions. Activation is per-slug; the agentic research pipeline and the
re-qualification endpoint always evaluate against the ACTIVE version.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..db import open_db
from ..icp_store import ICPStore

router = APIRouter(prefix="/api/v1/icps", tags=["icp"])


# Tenant resolution is unified in lead_engine.tenant (claims first;
# fail-closed without membership; env bridge for machine contexts).
from ..tenant import db_handle as get_db


class ICPCreateRequest(BaseModel):
    slug: str = Field(default="agentic", min_length=2, max_length=64,
                      pattern=r"^[a-z0-9][a-z0-9_-]*$")
    definition: dict = Field(..., description="full ICP dict: industry, cities, "
                             "keywords, criteria, v0_limits...")
    activate: bool = True
    source: str = Field(default="manual", pattern="^(manual|chat_intent|yaml_import)$")


@router.get("")
def list_icps(slug: str = "agentic", db=Depends(get_db)):
    return {"versions": ICPStore(db).list_versions(slug),
            "active": ICPStore(db).active(slug)}


@router.post("")
def create_icp(req: ICPCreateRequest, db=Depends(get_db)):
    icps = ICPStore(db)
    try:
        row = icps.create_version(req.slug, req.definition, source=req.source)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if req.activate:
        row = icps.activate(row["icp_version_id"])
    return {"icp": row}


@router.post("/{icp_version_id}/activate")
def activate_icp(icp_version_id: str, db=Depends(get_db)):
    icps = ICPStore(db)
    try:
        row = icps.activate(icp_version_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"icp": row}
