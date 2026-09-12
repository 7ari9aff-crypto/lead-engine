"""API surface for the event backbone: webhooks CRUD, notifications,
reconciliation. Events themselves dispatch from the event-worker."""
import base64
import os

from fastapi import Request, APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..config import load_env
from ..db import open_db
from ..secrets import encrypt_secret

load_env()

router = APIRouter(tags=["events"])


def get_db(request=None):
    """Request-scoped handle: resolves the tenant org from verified JWT
    claims (set by the app middleware) and falls back to the env bridge."""
    from ..db import open_db

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


def _org_id() -> str | None:
    return os.environ.get("LEAD_ENGINE_ORG_ID")


class WebhookRequest(BaseModel):
    url: str
    events: list[str] = ["*"]


@router.get("/api/v1/webhooks")
def list_webhooks(db=Depends(get_db)):
    org = _org_id()
    if not org:
        return {"webhooks": []}
    rows = db.query(
        "SELECT id, url, events, status, created_at FROM public.webhooks"
        " WHERE organization_id = ? ORDER BY created_at DESC", (org,))
    return {"webhooks": rows}


@router.post("/api/v1/webhooks")
def create_webhook(req: WebhookRequest, db=Depends(get_db)):
    org = _org_id()
    if not org:
        raise HTTPException(status_code=409, detail="no organization context")
    from urllib.parse import urlparse

    parsed = urlparse(req.url)
    loopback = parsed.hostname in ("127.0.0.1", "localhost", "::1")
    if parsed.scheme != "https" and not loopback:
        raise HTTPException(status_code=422, detail="webhook URL must be https")
    import secrets as _secrets

    raw_secret = "whsec_" + _secrets.token_hex(24)
    db.execute(
        "INSERT INTO public.webhooks (organization_id, url, secret_enc, events)"
        " VALUES (?,?,?,?)",
        (org, req.url, encrypt_secret(raw_secret), req.events))
    row = db.one(
        "SELECT id, url, events, status FROM public.webhooks"
        " WHERE organization_id = ? AND url = ? ORDER BY created_at DESC LIMIT 1",
        (org, req.url))
    # The signing secret is shown ONCE — like Stripe. It is not recoverable.
    return {**row, "signing_secret": raw_secret}


@router.delete("/api/v1/webhooks/{webhook_id}")
def delete_webhook(webhook_id: str, db=Depends(get_db)):
    org = _org_id()
    cur = db.execute(
        "DELETE FROM public.webhooks WHERE organization_id = ? AND id = ?",
        (org, webhook_id))
    if getattr(cur, "rowcount", 0) == 0:
        raise HTTPException(status_code=404, detail="webhook not found")
    return {"ok": True}


@router.get("/api/v1/notifications")
def list_notifications(limit: int = 50, db=Depends(get_db)):
    org = _org_id()
    if not org:
        return {"notifications": []}
    rows = db.query(
        "SELECT id, kind, title, body, read, created_at FROM notifications"
        " WHERE organization_id = ? ORDER BY created_at DESC LIMIT ?",
        (org, limit))
    for row in rows:
        if isinstance(row.get("body"), str):
            import json
            try:
                row["body"] = json.loads(row["body"])
            except json.JSONDecodeError:
                pass
    return {"notifications": rows}


@router.post("/api/v1/notifications/{notification_id}/read")
def mark_read(notification_id: int, db=Depends(get_db)):
    org = _org_id()
    db.execute("UPDATE notifications SET read = 1 WHERE id = ? AND organization_id = ?",
               (notification_id, org))
    return {"ok": True}


@router.get("/api/v1/billing/reconciliation")
def usage_reconciliation(db=Depends(get_db)):
    """Usage ledger (append-only truth) vs providers.quota_used (counters).
    Drift means a counter was reset or a write was lost — reconcile before
    trusting quota percentages for billing."""
    org = _org_id()
    ledger = db.query(
        "SELECT provider, task, COUNT(*) AS calls, SUM(units) AS units"
        " FROM usage_ledger GROUP BY provider, task ORDER BY provider")
    counters = db.query(
        "SELECT name, task, quota_used FROM providers ORDER BY name, task")
    counter_map = {(c["name"], c["task"]): c["quota_used"] for c in counters}
    report = []
    for row in ledger:
        counter = counter_map.get((row["provider"], row["task"]))
        drift = None if counter is None else round(float(counter) - float(row["units"] or 0), 3)
        report.append({**row, "counter_quota_used": counter, "drift": drift})
    drifted = [r for r in report if r["drift"] not in (None, 0, 0.0)]
    return {"lines": report, "drifted": drifted,
            "status": "drifted" if drifted else "reconciled"}
