"""Platform admin API: tenant provisioning (Phase 3 state machine).

Gated by PLATFORM_ADMIN_TOKEN — this is the control plane's control plane.
In production the token belongs to the billing/ops automation only.
"""
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from .. import provisioning
from ..config import load_env
from ..db import open_db

load_env()

router = APIRouter(tags=["platform"])


def _require_admin(request_headers) -> None:
    expected = os.environ.get("PLATFORM_ADMIN_TOKEN")
    if not expected:
        raise HTTPException(status_code=503, detail="platform admin disabled")
    provided = request_headers.get("x-platform-token", "")
    if provided != expected:
        raise HTTPException(status_code=401, detail="invalid platform token")


class ProvisionRequest(BaseModel):
    name: str
    slug: str
    isolation_level: str = "pooled"   # pooled | isolated_compute | dedicated


@router.post("/api/v1/platform/organizations")
def provision_tenant(req: ProvisionRequest, request: Request):
    _require_admin(request.headers)
    if req.isolation_level not in ("pooled", "isolated_compute", "dedicated"):
        raise HTTPException(status_code=422, detail="invalid isolation_level")
    db = open_db()
    try:
        existing = db.one("SELECT id FROM public.organizations WHERE slug = ?",
                          (req.slug,))
        if existing:
            raise HTTPException(status_code=409, detail="slug already exists")
        row = db.one(
            "INSERT INTO public.organizations (name, slug, isolation_level)"
            " VALUES (?,?,?) RETURNING id",
            (req.name, req.slug, req.isolation_level))
        org_id = row["id"]
        result = provisioning.provision(db, org_id,
                                        isolation_level=req.isolation_level)
        return result
    finally:
        db.conn.close()


@router.get("/api/v1/platform/organizations/{org_id}/provisioning")
def provisioning_status(org_id: str, request: Request):
    _require_admin(request.headers)
    db = open_db()
    try:
        row = provisioning.status(db, org_id)
        if not row:
            raise HTTPException(status_code=404, detail="no provisioning record")
        return row
    finally:
        db.conn.close()
