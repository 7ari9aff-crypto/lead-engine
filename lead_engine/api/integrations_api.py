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

from fastapi import APIRouter, Depends, HTTPException

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


def get_org_id() -> str:
    """Phase 1 single-org bridge: every route resolves the tenant from env."""
    org_id = os.environ.get("LEAD_ENGINE_ORG_ID")
    if not org_id:
        raise HTTPException(status_code=503,
                            detail="LEAD_ENGINE_ORG_ID is not configured")
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
