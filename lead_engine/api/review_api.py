"""Stage 3 — Human review API.

GET  /api/v1/review/pending?job_id=   the review board: presentation payloads
                                      for a research job's leads
GET  /api/v1/leads/{lead_id}/presentation          full interpretation layer
POST /api/v1/leads/{lead_id}/decision              THE human gate:
                                       APPROVE_CONTACT | REJECT |
                                       RESEARCH_MORE | SAVE_FOR_LATER
POST /api/v1/leads/{lead_id}/requalify             re-qualify from stored
                                       facts against an (updated) ICP —
                                       never re-discovers (directive §25)

Hard rules enforced here:
- APPROVE_CONTACT is the TERMINAL state of the current system; nothing sends
  anything, ever (directive §45).
- Every decision is audit-logged (actor + action + payload) and emitted on
  the event backbone.
- The decision columns are human-owned: pipeline refreshes never touch them.
"""
import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..db import utcnow
from ..research.presentation import build_presentation
from ..truth import FactsStore

router = APIRouter(tags=["stage3-review"])

DECISIONS = ("APPROVE_CONTACT", "REJECT", "RESEARCH_MORE", "SAVE_FOR_LATER")


# Tenant resolution is unified in lead_engine.tenant (claims first;
# fail-closed for users with no membership; env bridge for machine contexts).
from ..tenant import db_handle as get_db


def _actor(request: Request) -> str:
    claims = getattr(request.state, "claims", None)
    if claims:
        return str(claims.get("sub") or claims.get("email") or "authenticated")
    return "dev-open"


def _get_lead(db, lead_id: str) -> dict:
    org_sql, org_params = "", []
    org = getattr(db, "org_id", None)
    if getattr(db, "dialect", "sqlite") == "sqlite":
        org_sql, org_params = " AND organization_id = ?", [org or "shared"]
    elif org:
        org_sql, org_params = " AND organization_id = ?", [org]
    lead = db.one(f"SELECT * FROM leads WHERE lead_id=?{org_sql}",
                  (lead_id, *org_params))
    if not lead:
        raise HTTPException(status_code=404, detail="lead not found")
    return lead


class DecisionRequest(BaseModel):
    action: str = Field(..., pattern="^(APPROVE_CONTACT|REJECT|RESEARCH_MORE|SAVE_FOR_LATER)$")
    note: str | None = None


@router.get("/api/v1/review/pending")
def review_pending(request: Request, job_id: str | None = None,
                   db=Depends(get_db)):
    store = FactsStore(db)
    sql, params = "SELECT * FROM leads WHERE 1=1", []
    org = getattr(db, "org_id", None)
    if getattr(db, "dialect", "sqlite") == "sqlite":
        sql += " AND organization_id = ?"
        params.append(org or "shared")
    elif org:
        sql += " AND organization_id = ?"
        params.append(org)
    if job_id:
        sql += " AND job_id = ?"
        params.append(job_id)
    sql += " ORDER BY COALESCE(qualification_score, score) DESC LIMIT 200"
    return {
        "leads": [
            build_presentation(db, lead, store=store) for lead in db.query(sql, params)
        ]
    }


@router.get("/api/v1/leads/{lead_id}/presentation")
def lead_presentation(lead_id: str, db=Depends(get_db)):
    lead = _get_lead(db, lead_id)
    return build_presentation(db, lead)


@router.post("/api/v1/leads/{lead_id}/decision")
def lead_decision(lead_id: str, req: DecisionRequest, request: Request,
                  background: BackgroundTasks, db=Depends(get_db)):
    lead = _get_lead(db, lead_id)
    actor = _actor(request)
    now = utcnow()

    new_job_id = None
    if req.action == "RESEARCH_MORE":
        # continue the SAME research context: facts are subject-keyed, so a
        # focused child job resumes with everything already known
        from ..research import ResearchJobManager

        manager = ResearchJobManager(db)
        subject = lead.get("domain") or lead.get("name") or lead_id
        objective = f"عمّق البحث عن {subject}"
        if req.note:
            objective += f" — {req.note[:200]}"
        new_job_id = manager.create(objective, parent_job_id=lead.get("job_id"))
        from ..queue import enqueue, platform_mode

        if platform_mode():
            enqueue(db, new_job_id)
        else:
            from .research_api import _run_research

            background.add_task(_run_research, new_job_id)

    db.execute(
        "UPDATE leads SET disposition=?, disposition_note=?, disposition_at=?,"
        " decided_by=?, updated_at=? WHERE lead_id=?",
        (req.action, req.note, now, actor, now, lead_id))
    db.audit(actor, f"lead.{req.action.lower()}", "lead", lead_id, {
        "action": req.action, "note": req.note, "job_id": lead.get("job_id"),
        "child_job_id": new_job_id,
    })
    try:
        from ..events import emit
        import os

        emit(db, getattr(db, "org_id", None) or
             os.environ.get("LEAD_ENGINE_ORG_ID"),
             f"lead.{req.action.lower()}", "lead", lead_id,
             {"lead_id": lead_id, "actor": actor, "note": req.note,
              "child_job_id": new_job_id})
    except Exception:
        pass  # events never break the decision
    return {"ok": True, "lead_id": lead_id, "action": req.action,
            "child_job_id": new_job_id,
            "note": "APPROVE_CONTACT هو آخر خطوة في النظام الحالي — "
                    "لا يوجد أي إرسال تلقائي" if req.action == "APPROVE_CONTACT" else None}


class RequalifyRequest(BaseModel):
    icp_version_id: str | None = None


@router.post("/api/v1/leads/{lead_id}/requalify")
def lead_requalify(lead_id: str, req: RequalifyRequest, request: Request,
                   db=Depends(get_db)):
    """ICP changed? Re-evaluate the stored facts against the (new) ICP.
    Facts are already on disk — no discovery, no new search spend."""
    lead = _get_lead(db, lead_id)
    from ..icp_store import ICPStore
    from ..router import Router
    from ..cache import CacheLayer
    from ..config import load_settings, load_cache_policy
    from ..research.qualification import QualificationError, qualify_from_facts

    icps = ICPStore(db)
    if req.icp_version_id:
        row = icps.get(req.icp_version_id)
        if not row:
            raise HTTPException(status_code=404, detail="ICP version not found")
        icp = row["definition"]
    else:
        row = icps.active("agentic")
        if not row:
            raise HTTPException(status_code=409, detail="no active ICP version")
        icp = row["definition"]

    router = Router(db, CacheLayer(db, load_cache_policy()), load_settings())
    try:
        verdict = qualify_from_facts(db, router, "company",
                                     _subject_id(lead), icp)
    except QualificationError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    raw = lead.get("raw")
    raw_dict = {}
    if isinstance(raw, str):
        try:
            raw_dict = json.loads(raw)
        except json.JSONDecodeError:
            raw_dict = {}
    elif isinstance(raw, dict):
        raw_dict = raw
    pipeline = raw_dict.get("pipeline") or {}
    pipeline["qualification"] = verdict
    raw_dict["pipeline"] = pipeline

    db.execute(
        "UPDATE leads SET qualification_score=?, tier=?, processing_mode=?,"
        " raw=?, updated_at=? WHERE lead_id=?",
        (verdict["fit_score"], verdict["tier"],
         verdict.get("processing_mode", "cloud"),
         json.dumps(raw_dict, ensure_ascii=False, default=str), utcnow(), lead_id))
    db.audit(_actor(request), "lead.requalified", "lead", lead_id, {
        "icp_version_id": req.icp_version_id,
        "fit_score": verdict["fit_score"], "tier": verdict["tier"]})
    lead = _get_lead(db, lead_id)
    return {"ok": True, "presentation": build_presentation(db, lead)}


def _subject_id(lead: dict) -> str:
    from ..research.tools import canonical_subject

    _, subject = canonical_subject({"name": lead.get("name"),
                                    "domain": lead.get("domain")})
    return subject

class ResolveConflictRequest(BaseModel):
    winner_fact_id: str
    note: str | None = None


@router.get("/api/v1/conflicts")
def list_conflicts(subject_id: str | None = None, field: str | None = None,
                   status: str = "OPEN", db=Depends(get_db)):
    """List detected fact conflicts for human review."""
    store = FactsStore(db)
    return {"conflicts": store.conflicts(subject_id=subject_id, field=field, status=status)}


@router.post("/api/v1/conflicts/{conflict_id}/resolve")
def resolve_conflict_endpoint(conflict_id: str, req: ResolveConflictRequest,
                              request: Request, db=Depends(get_db)):
    """Human gate to resolve a factual conflict: winner -> VERIFIED, loser -> STALE."""
    store = FactsStore(db)
    actor = _actor(request)
    try:
        resolved = store.resolve_conflict(
            conflict_id,
            req.winner_fact_id,
            note=req.note,
            by=actor,
            automatic=False,
        )
        db.audit(actor, "conflict.resolved", "fact_conflict", conflict_id, {
            "winner": req.winner_fact_id, "note": req.note,
            "subject_id": resolved.get("subject_id"),
        })
        return {"ok": True, "conflict": resolved}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
