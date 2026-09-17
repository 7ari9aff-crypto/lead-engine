"""Billing layer â€” Stripe webhook signature + plan â†’ limits application.

Pinned behaviour:
  * the plan catalog maps every plan to the entitlement keys get_limits reads,
  * priceâ†’plan wiring resolves from env, unknown prices resolve to None,
  * the webhook is fail-closed: 503 when unconfigured, 400 on a bad or
    replayed Stripe-Signature,
  * checkout.session.completed upgrades organizations.limits (get_limits
    sees the new plan immediately),
  * subscription deletion downgrades back to platform defaults.
"""
import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient

from lead_engine.api import billing_api
from lead_engine.api.app import app
from lead_engine.db import Database
from lead_engine.entitlements import get_limits
from lead_engine.policy import DEFAULT_LIMITS


@pytest.fixture()
def db_path(tmp_path):
    """Hermetic SQLite file. The webhook closes the handle it opens, so the
    factory must return a *fresh* Database per call â€” tests re-open the same
    file to assert on the committed state."""
    path = tmp_path / "billing.sqlite3"
    db = Database(path)
    db.execute(
        "CREATE TABLE IF NOT EXISTS organizations (id TEXT PRIMARY KEY, limits TEXT)")
    db.execute("INSERT INTO organizations (id) VALUES ('org-1')")
    db.conn.commit()
    db.conn.close()
    return path


@pytest.fixture()
def client(db_path, monkeypatch):
    # The webhook opens its own handle (it runs outside request scope);
    # pin that factory to the hermetic test database.
    monkeypatch.setattr(billing_api, "open_db", lambda: Database(db_path))
    return TestClient(app)


def _limits(db_path):
    return get_limits(Database(db_path), "org-1")


def _signed(payload: bytes, secret: str, ts: int | None = None) -> str:
    """Build a Stripe-Signature header the same way Stripe does (t=â€¦,v1=â€¦)."""
    ts = int(time.time()) if ts is None else ts
    signed = f"{ts}.".encode() + payload
    digest = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={digest}"


# ---------------------------------------------------------------------------
# Plan catalog
# ---------------------------------------------------------------------------

_REQUIRED_KEYS = {"max_jobs_per_day", "max_leads_per_month",
                  "max_provider_calls_per_day", "channels"}


def test_plan_catalog_covers_entitlement_keys():
    for plan, spec in billing_api.PLANS.items():
        assert _REQUIRED_KEYS <= set(spec), plan
    assert billing_api.PLANS["pro"]["max_jobs_per_day"] \
        > billing_api.PLANS["free"]["max_jobs_per_day"]


def test_plan_for_price_resolves_from_env(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro_123")
    monkeypatch.delenv("STRIPE_PRICE_BUSINESS", raising=False)
    assert billing_api.plan_for_price("price_pro_123") == "pro"
    assert billing_api.plan_for_price("price_unknown") is None


def test_checkout_without_stripe_key_is_explicit_503(client, monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    resp = client.post("/api/v1/billing/checkout", json={"plan": "pro"})
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Webhook â€” fail-closed signature enforcement
# ---------------------------------------------------------------------------

def test_webhook_unconfigured_returns_503(client, monkeypatch):
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    resp = client.post("/api/v1/billing/webhook", content=b"{}")
    assert resp.status_code == 503


def test_webhook_rejects_bad_signature(client, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    resp = client.post("/api/v1/billing/webhook", content=b"{}",
                       headers={"Stripe-Signature": "t=1,v1=deadbeef"})
    assert resp.status_code == 400


def test_webhook_rejects_replayed_signature(client, monkeypatch):
    """A valid signature with a timestamp outside the tolerance window is a
    replay â€” rejected even though the HMAC itself is correct."""
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    payload = json.dumps({"type": "checkout.session.completed",
                          "data": {"object": {"client_reference_id": "org-1",
                                              "metadata": {"plan": "pro"}}}}).encode()
    old_sig = _signed(payload, "whsec_test", ts=int(time.time()) - 3600)
    resp = client.post("/api/v1/billing/webhook", content=payload,
                       headers={"Stripe-Signature": old_sig})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Webhook â€” the single write path
# ---------------------------------------------------------------------------

_UPGRADE = {
    "type": "checkout.session.completed",
    "data": {"object": {"client_reference_id": "org-1",
                        "metadata": {"plan": "pro"}}},
}

_DOWNGRADE = {
    "type": "customer.subscription.deleted",
    "data": {"object": {"metadata": {"org_id": "org-1"}}},
}


def _post_event(client, monkeypatch, event: dict):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    payload = json.dumps(event).encode()
    return client.post("/api/v1/billing/webhook", content=payload,
                       headers={"Stripe-Signature": _signed(payload, "whsec_test")})


def test_webhook_upgrade_applies_pro_limits(client, db_path, monkeypatch):
    resp = _post_event(client, monkeypatch, _UPGRADE)
    assert resp.status_code == 200
    assert resp.json() == {"received": True, "org": "org-1", "plan": "pro"}
    # The upgrade is visible to entitlements immediately.
    assert _limits(db_path)["max_jobs_per_day"] \
        == billing_api.PLANS["pro"]["max_jobs_per_day"]


def test_webhook_downgrade_restores_defaults(client, db_path, monkeypatch):
    _post_event(client, monkeypatch, _UPGRADE)
    resp = _post_event(client, monkeypatch, _DOWNGRADE)
    assert resp.status_code == 200
    assert resp.json()["plan"] == "free"
    # limits is NULL again â†’ get_limits falls back to platform defaults.
    assert _limits(db_path)["max_jobs_per_day"] \
        == DEFAULT_LIMITS["max_jobs_per_day"]


def test_webhook_unknown_plan_is_skipped_not_applied(client, db_path, monkeypatch):
    event = {"type": "checkout.session.completed",
             "data": {"object": {"client_reference_id": "org-1",
                                 "metadata": {"plan": "enterprise"}}}}
    resp = _post_event(client, monkeypatch, event)
    assert resp.status_code == 200
    assert resp.json().get("skipped")
    # DB untouched â€” still on defaults.
    assert _limits(db_path)["max_jobs_per_day"] \
        == DEFAULT_LIMITS["max_jobs_per_day"]


def test_webhook_event_without_org_reference_is_ignored(client, db_path, monkeypatch):
    event = {"type": "checkout.session.completed",
             "data": {"object": {"metadata": {"plan": "pro"}}}}
    resp = _post_event(client, monkeypatch, event)
    assert resp.status_code == 200
    assert resp.json().get("skipped") == "no org reference"

