"""Retention / deletion / export — data governance endpoints (Phase 2).

Rules (docs/architecture.md: Data Governance):
- soft delete here = stage REJECTED + purge flag; hard delete removes rows.
- purge_expired removes leads past the org retention window.
- export returns the org's leads as JSON (portability right).
"""
import json
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from ..db import open_db
from ..entitlements import get_limits

router = APIRouter(tags=["data-governance"])


def get_db():
    db = open_db()
    try:
        yield db
    finally:
        db.conn.close()


def _org_id() -> str | None:
    return os.environ.get("LEAD_ENGINE_ORG_ID")


@router.delete("/api/v1/leads/{lead_id}")
def delete_lead(lead_id: str, db=Depends(get_db)):
    """Hard delete a single lead (org-scoped). Evidence follows the lead."""
    org = _org_id()
    row = db.one("SELECT lead_id FROM leads WHERE lead_id = ? AND organization_id = ?",
                 (lead_id, org))
    if not row:
        raise HTTPException(status_code=404, detail="lead not found")
    db.execute("DELETE FROM evidence WHERE lead_id = ?", (lead_id,))
    db.execute("DELETE FROM leads WHERE lead_id = ? AND organization_id = ?",
               (lead_id, org))
    return {"ok": True, "deleted": lead_id}


@router.get("/api/v1/data/export")
def export_org_data(db=Depends(get_db)):
    """Full org data export (portability): leads + jobs + suppression."""
    org = _org_id()
    if not org:
        raise HTTPException(status_code=409, detail="no organization context")
    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "leads": db.query("SELECT * FROM leads WHERE organization_id = ?", (org,)),
        "jobs": db.query("SELECT job_id, icp_id, state, created_at, updated_at"
                         " FROM jobs WHERE organization_id = ?", (org,)),
        "suppression": db.query(
            "SELECT channel, value, reason, created_at"
            " FROM public.suppression_entries WHERE organization_id = ?", (org,)),
    }


@router.post("/api/v1/data/purge-expired")
def purge_expired(db=Depends(get_db)):
    """Delete leads past the org retention window (default 30 days,
    override via organizations.limits.retention_days)."""
    org = _org_id()
    if not org:
        raise HTTPException(status_code=409, detail="no organization context")
    limits = get_limits(db, org)
    days = int(limits.get("retention_days", 30))
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    expired = db.query(
        "SELECT lead_id FROM leads WHERE organization_id = ? AND created_at < ?",
        (org, cutoff))
    for row in expired:
        db.execute("DELETE FROM evidence WHERE lead_id = ?", (row["lead_id"],))
    cur = db.execute(
        "DELETE FROM leads WHERE organization_id = ? AND created_at < ?",
        (org, cutoff))
    return {"purged": getattr(cur, "rowcount", 0), "retention_days": days,
            "cutoff": cutoff}
