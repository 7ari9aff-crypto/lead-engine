"""HTTP surface for the OAuth Integration Platform — FastAPI router.

Endpoints (tenant context from LEAD_ENGINE_ORG_ID):
  GET  /api/v1/integrations                        status for every registry provider
  POST /api/v1/integrations/{provider}/connect     -> {authorize_url, state}
  GET  /api/v1/integrations/{provider}/callback    OAuth redirect target -> {connected: true}
  POST /api/v1/integrations/{provider}/revoke      -> revoke + clear tokens

404 for unknown providers, 409 for known-but-unconfigured/disabled ones,
400 when the OAuth callback fails (bad state, provider rejection) — the
connection row carries the provider's detail in last_error.
"""
import os

import requests

from fastapi import APIRouter, Depends, HTTPException, Request

from .. import integrations
from ..db import Database, open_db

router = APIRouter(tags=["integrations"])


def get_db():
    """Local DI — same connection style as app.py:get_db; kept local to avoid
    a circular import (mirrors activity/api.py)."""
    db = open_db()
    try:
        yield db
    finally:
        db.conn.close()


def get_org_id(request: Request, db: Database = Depends(get_db)) -> str:
    """Tenant from the unified resolver: verified claims first (fail-closed),
    env bridge only for token-less machine contexts."""
    from ..tenant import apply_context

    apply_context(db, request)
    org_id = getattr(db, "org_id", None)
    if not org_id or str(org_id).startswith("__"):
        raise HTTPException(status_code=503,
                            detail="no organization context")
    return org_id


def _default_redirect_uri(provider: str) -> str:
    base = (os.environ.get("LEAD_ENGINE_PUBLIC_BASE_URL") or "").rstrip("/")
    return f"{base}/api/v1/integrations/{provider}/callback" if base else ""


@router.get("/api/v1/integrations")
def list_integrations(db: Database = Depends(get_db),
                      org_id: str = Depends(get_org_id)):
    """Registry-wide integration status for the org: configured = platform
    OAuth app present, connected/status/scopes/expires_at from the stored row."""
    stored = integrations.connections_for_org(db, org_id)
    out = []
    for name in integrations.PROVIDERS:
        row = stored.get(name) or {}
        out.append({
            "provider": name,
            "configured": integrations.is_configured(name),
            "connected": row.get("status") == "connected",
            "status": row.get("status") or "not_connected",
            "scopes": row.get("scopes") or [],
            "expires_at": row.get("expires_at"),
        })
    return {"integrations": out}


@router.post("/api/v1/integrations/{provider}/connect")
def start_connect(provider: str, redirect_uri: str | None = None,
                  db: Database = Depends(get_db),
                  org_id: str = Depends(get_org_id)):
    """Create the pending connection + signed state and hand back the
    provider authorize URL the browser must be redirected to."""
    if provider not in integrations.PROVIDERS:
        raise HTTPException(status_code=404, detail=f"unknown provider: {provider}")
    if not integrations.is_configured(provider):
        raise HTTPException(status_code=409,
                            detail=f"provider not configured or disabled: {provider}")
    redirect = (redirect_uri or "").strip() or _default_redirect_uri(provider)
    if not redirect:
        raise HTTPException(
            status_code=422,
            detail="redirect_uri is required (or set LEAD_ENGINE_PUBLIC_BASE_URL)")
    try:
        url, state = integrations.build_authorization_url(db, org_id, provider, redirect)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"authorize_url": url, "state": state, "redirect_uri": redirect}


@router.get("/api/v1/integrations/{provider}/callback")
def oauth_callback(provider: str, code: str = "", state: str = "",
                   redirect_uri: str | None = None,
                   db: Database = Depends(get_db),
                   org_id: str = Depends(get_org_id)):
    """OAuth redirect target: verify the state, exchange the code for tokens,
    store them encrypted. Any failure becomes HTTP 400 with the detail."""
    if provider not in integrations.PROVIDERS:
        raise HTTPException(status_code=404, detail=f"unknown provider: {provider}")
    if not code or not state:
        raise HTTPException(status_code=400, detail="code and state are required")
    try:
        integrations.handle_callback(db, org_id, provider, code, state,
                                     redirect_uri=redirect_uri or None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"connected": True, "provider": provider}


@router.post("/api/v1/integrations/{provider}/revoke")
def revoke(provider: str, db: Database = Depends(get_db),
           org_id: str = Depends(get_org_id)):
    """Revoke the org's connection: status='revoked', token columns cleared."""
    if provider not in integrations.PROVIDERS:
        raise HTTPException(status_code=404, detail=f"unknown provider: {provider}")
    connection = integrations.revoke_connection(db, org_id, provider)
    if connection is None:
        raise HTTPException(status_code=404, detail="connection not found")
    return {"provider": provider, "connected": False, "status": "revoked"}


@router.post("/api/v1/integrations/hubspot/push-leads")
def hubspot_push_leads(request: Request, dry_run: bool = True, limit: int = 500,
                       db: Database = Depends(get_db),
                       org_id: str = Depends(get_org_id)):
    """Push ACCEPTED leads to the org's connected HubSpot (upsert by email).

    Safety contract (see lead_engine/crm_push.py):
      * ``dry_run`` defaults to TRUE: the caller must opt in to send data.
      * admin-only (the static machine token is not allowed on this route).
      * tenant-scoped; erased / suppressed / reviewer-rejected / INVALID-email
        leads are never sent.
    """
    from .app import require_admin
    require_admin(request, db)
    if getattr(request.state, "machine", False):
        raise HTTPException(status_code=403,
                            detail="machine token is not permitted on this route")
    if not 1 <= limit <= 2000:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 2000")

    from .. import crm_push
    from ..policy import Suppression
    from ..tenant import org_clause

    clause, params = org_clause(db)
    rows = db.query(
        "SELECT lead_id, name, domain, city, country, industry, phone, email,"
        " email_status, decision_maker, decision_maker_title, linkedin, website,"
        " stage, legal_decision, disposition FROM leads WHERE stage = 'ACCEPTED'"
        f"{clause} ORDER BY score DESC LIMIT ?", list(params) + [limit])

    def access_token() -> str:
        try:
            return integrations.get_valid_access_token(db, org_id, "hubspot")
        except ConnectionError as exc:
            raise HTTPException(status_code=409,
                                detail=f"hubspot not connected: {exc}") from exc

    if not dry_run:
        access_token()  # fail fast with 409 before building any payload

    def is_suppressed(email: str):
        # FAIL CLOSED: if the do-not-contact list cannot be read, sending
        # would risk contacting people who opted out. Stop, do not guess.
        try:
            return Suppression.is_suppressed(db, org_id, "email", email)
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail="suppression list unavailable; refusing to push") from exc

    result = crm_push.push(
        rows,
        is_suppressed=is_suppressed,
        access_token=access_token,
        http_post=requests.post,
        dry_run=dry_run,
    )
    if not dry_run:
        db.audit("operator", "crm.hubspot.push", "organization", org_id, {
            "pushed": result["pushed"], "eligible": result["eligible"],
            "skipped": result["skipped"], "failed_batches": len(result["failed_batches"]),
        })
    # never return per-lead detail beyond ids + reason codes
    return result
