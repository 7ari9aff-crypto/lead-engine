"""Billing layer — closes the Stripe gap (plan-improvement T6, architecture §6).

Design (matches the frozen baseline: "subscriptions synchronize limits, they
never compute them"):

* ``GET  /api/v1/billing/plans``    — plan catalog with the limits each plan
  maps to (the Pricing page renders from this; API and UI cannot disagree).
* ``POST /api/v1/billing/checkout`` — creates a Stripe Checkout Session via
  the plain REST API (``requests``, already a dependency — no stripe SDK).
  Returns the hosted checkout URL the frontend redirects to.
* ``POST /api/v1/billing/webhook``  — the single write path. Verifies the
  ``Stripe-Signature`` HMAC (t=…,v1=…), then maps price → plan → limits and
  updates ``organizations.limits`` jsonb, which ``entitlements.get_limits``
  already reads. Subscription deletion downgrades to the free plan.

Fail-safe by construction: without STRIPE_SECRET_KEY the checkout endpoint
returns 503 and the webhook endpoint returns 503 (nothing is silently
ignored); entitlements keep falling back to DEFAULT_LIMITS so the engine
never blocks on billing being unconfigured.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..db import open_db
from ..observability import get_logger
from ..policy import _t

router = APIRouter(tags=["billing"])
log = get_logger("lead_engine.api.billing")

# ---------------------------------------------------------------------------
# Plan catalog — the single source both the checkout and the webhook use.
# Values are *overrides* merged over policy.DEFAULT_LIMITS by get_limits().
# ---------------------------------------------------------------------------

PLANS: dict[str, dict[str, Any]] = {
    "free": {
        "label": "المجانية",
        "max_jobs_per_day": 3,
        "max_leads_per_month": 500,
        "max_provider_calls_per_day": 500,
        "channels": ["email"],
    },
    "pro": {
        "label": "Pro",
        "max_jobs_per_day": 25,
        "max_leads_per_month": 20_000,
        "max_provider_calls_per_day": 8_000,
        "channels": ["email"],
    },
    "business": {
        "label": "Business",
        "max_jobs_per_day": 100,
        "max_leads_per_month": 100_000,
        "max_provider_calls_per_day": 40_000,
        "channels": ["email", "whatsapp"],
    },
}

# Stripe price IDs come from env so the same code serves test/live mode.
_PRICE_ENV = {"pro": "STRIPE_PRICE_PRO", "business": "STRIPE_PRICE_BUSINESS"}

_STRIPE_API = "https://api.stripe.com/v1"
_WEBHOOK_TOLERANCE_S = 300  # replay guard: reject events older than 5 minutes


def _secret() -> str | None:
    return os.environ.get("STRIPE_SECRET_KEY") or None


def _webhook_secret() -> str | None:
    return os.environ.get("STRIPE_WEBHOOK_SECRET") or None


def plan_for_price(price_id: str) -> str | None:
    """Map a Stripe price ID to a plan name via the env wiring."""
    for plan, env in _PRICE_ENV.items():
        if price_id and price_id == os.environ.get(env):
            return plan

# ---------------------------------------------------------------------------
# Checkout — creates a Stripe Checkout Session via plain REST (`requests` is
# already a dependency; adding the stripe SDK for two endpoints is dead weight).
# ---------------------------------------------------------------------------

class CheckoutRequest(BaseModel):
    plan: str  # "pro" | "business" — free has nothing to buy


def _resolve_org_id(db, request: Request) -> str | None:
    claims = getattr(request.state, "claims", None)
    if claims:
        from . import auth_jwt

        return auth_jwt.resolve_org_id(claims, db)
    return os.environ.get("LEAD_ENGINE_ORG_ID")


@router.get("/api/v1/billing/plans")
def list_plans():
    """Plan catalog for the Pricing page. Public by design: it is marketing
    data (labels + limits) — no tenant data, no secrets."""
    return {
        "plans": [
            {"id": plan, **body, "price_env": _PRICE_ENV.get(plan)}
            for plan, body in PLANS.items()
        ]
    }


@router.post("/api/v1/billing/checkout")
def create_checkout(req: CheckoutRequest, request: Request):
    secret = _secret()
    if not secret:
        raise HTTPException(status_code=503, detail="billing غير مُهيَّأ على هذا الخادم")
    if req.plan not in _PRICE_ENV:
        raise HTTPException(status_code=422, detail="خطة غير معروفة")

    db = open_db()
    try:
        org_id = _resolve_org_id(db, request)
    finally:
        db.conn.close()
    if not org_id:
        raise HTTPException(status_code=401, detail="لا توجد مؤسسة مرتبطة بالجلسة")

    price_id = os.environ.get(_PRICE_ENV[req.plan], "")
    if not price_id:
        raise HTTPException(status_code=503,
                            detail=f"متغير البيئة {_PRICE_ENV[req.plan]} غير مضبوط")

    base_url = os.environ.get("LEAD_ENGINE_PUBLIC_BASE_URL", "").rstrip("/")
    import requests

    try:
        resp = requests.post(
            f"{_STRIPE_API}/checkout/sessions",
            auth=(secret, ""),
            data={
                "mode": "subscription",
                "line_items[0][price]": price_id,
                "line_items[0][quantity]": 1,
                "client_reference_id": org_id,
                "metadata[org_id]": org_id,
                "metadata[plan]": req.plan,
                "success_url": f"{base_url}/pricing?checkout=success",
                "cancel_url": f"{base_url}/pricing?checkout=cancelled",
            },
            timeout=15,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Stripe غير قابل للوصول: {exc}") from exc
    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Stripe رفض الطلب: {resp.text[:200]}")
    return {"checkout_url": resp.json().get("url")}


# ---------------------------------------------------------------------------
# Webhook — the single write path. Verifies the Stripe-Signature HMAC
# (t=timestamp,v1=hex), rejects replays, maps price → plan → limits, and
# updates organizations.limits which get_limits() already reads.
# ---------------------------------------------------------------------------

def _verify_signature(payload: bytes, header: str, secret: str) -> bool:
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        ts = int(parts["t"])
        expected = parts["v1"]
    except (ValueError, KeyError):
        return False
    if abs(time.time() - ts) > _WEBHOOK_TOLERANCE_S:
        return False  # replay guard
    signed = f"{ts}.{payload.decode('utf-8', errors='replace')}".encode()
    digest = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, expected)


def _apply_plan(db, org_id: str, plan: str) -> None:
    tbl = _t(db, "organizations")
    if plan == "free":
        # Subscription ended → back to platform defaults (NULL = inherit).
        db.execute(f"UPDATE {tbl} SET limits = NULL WHERE id = ?", (org_id,))
    else:
        db.execute(f"UPDATE {tbl} SET limits = ? WHERE id = ?",
                   (json.dumps(PLANS[plan]), org_id))


@router.post("/api/v1/billing/webhook")
async def stripe_webhook(request: Request):
    secret = _webhook_secret()
    if not secret:
        # Explicit 503, never a silent 200: a silent OK would let Stripe drop
        # the event from retries while the DB was never updated.
        raise HTTPException(status_code=503, detail="webhook غير مُهيَّأ")

    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    if not _verify_signature(payload, sig, secret):
        raise HTTPException(status_code=400, detail="توقيع غير صالح")

    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="payload ليس JSON صالح")

    etype = event.get("type", "")
    obj = (event.get("data") or {}).get("object") or {}

    # Resolve the org: client_reference_id on sessions, metadata elsewhere.
    org_id = obj.get("client_reference_id") or (obj.get("metadata") or {}).get("org_id")
    if not org_id:
        return {"received": True, "skipped": "no org reference"}

    if etype == "checkout.session.completed":
        plan = (obj.get("metadata") or {}).get("plan")
        if plan not in PLANS:
            return {"received": True, "skipped": f"unknown plan {plan!r}"}
    elif etype in ("customer.subscription.deleted", "customer.subscription.paused"):
        plan = "free"
    else:
        return {"received": True, "ignored": etype}

    db = open_db()
    try:
        _apply_plan(db, org_id, plan)
        db.conn.commit()
    finally:
        db.conn.close()
    log.info("billing.plan_applied", org_id=org_id, plan=plan, event=etype)
    return {"received": True, "org": org_id, "plan": plan}
