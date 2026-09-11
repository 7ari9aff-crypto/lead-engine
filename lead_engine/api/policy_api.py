"""Outreach safety API: suppression management + policy preview + entitlements.

The gate itself (PolicyGate.evaluate) runs before any outbound send; these
endpoints manage the list and let the dashboard preview decisions.
"""
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..db import open_db
from ..entitlements import get_limits
from ..policy import PolicyGate, Suppression

router = APIRouter(tags=["outreach-safety"])


def get_db():
    db = open_db()
    try:
        yield db
    finally:
        db.conn.close()


def _org_id() -> str | None:
    return os.environ.get("LEAD_ENGINE_ORG_ID")


class SuppressionRequest(BaseModel):
    channel: str = "email"
    value: str
    reason: str = "manual"


class EvaluateRequest(BaseModel):
    channel: str = "email"
    value: str
    recent_sends: int = 0
    baseline_per_hour: int = 0


@router.get("/api/v1/suppression")
def list_suppression(channel: str | None = None, limit: int = 200,
                     db=Depends(get_db)):
    org = _org_id()
    if not org:
        return {"entries": [], "note": "no org context"}
    sql = ("SELECT id, channel, value, reason, source, created_at"
           " FROM public.suppression_entries WHERE organization_id = ?")
    params: list = [org]
    if channel:
        sql += " AND channel IN (?, 'all')"
        params.append(channel)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    return {"entries": db.query(sql, params)}


@router.post("/api/v1/suppression")
def add_suppression(req: SuppressionRequest, db=Depends(get_db)):
    org = _org_id()
    if not org:
        raise HTTPException(status_code=409, detail="no organization context")
    return Suppression.add(db, org, req.channel, req.value, req.reason)


@router.delete("/api/v1/suppression/{entry_id}")
def delete_suppression(entry_id: str, db=Depends(get_db)):
    org = _org_id()
    if not org:
        raise HTTPException(status_code=409, detail="no organization context")
    if not Suppression.remove(db, org, entry_id):
        raise HTTPException(status_code=404, detail="entry not found")
    return {"ok": True}


@router.post("/api/v1/policy/evaluate")
def policy_evaluate(req: EvaluateRequest, db=Depends(get_db)):
    org = _org_id()
    decision = PolicyGate.evaluate(db, org, req.channel, req.value,
                                   recent_sends=req.recent_sends,
                                   baseline_per_hour=req.baseline_per_hour)
    return {"decision": decision.decision, "reasons": decision.reasons,
            "checks": decision.checks}


@router.get("/api/v1/entitlements")
def entitlements(db=Depends(get_db)):
    org = _org_id()
    limits = get_limits(db, org)
    return {"organization_id": org, "limits": limits}
