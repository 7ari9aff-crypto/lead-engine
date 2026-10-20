"""Billing logic bugs found in the partner review (2026-10-20).

B1  checkout must stamp org_id on the SUBSCRIPTION itself, otherwise Stripe's
    customer.subscription.* events carry no org reference and cancellations
    are silently skipped -> customer keeps a paid plan for free.
B2  the plan granted must follow the PRICE actually paid, not a metadata
    string, so a mismatched session can never grant a bigger plan.
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
    path = tmp_path / "b.sqlite3"
    db = Database(path)
    db.execute("CREATE TABLE IF NOT EXISTS organizations (id TEXT PRIMARY KEY, limits TEXT,"
               " stripe_customer_id TEXT, stripe_subscription_id TEXT)")
    db.execute("INSERT INTO organizations (id) VALUES ('org-1')")
    db.conn.commit()
    db.conn.close()
    return path


@pytest.fixture()
def client(db_path, monkeypatch):
    monkeypatch.setattr(billing_api, "open_db", lambda: Database(db_path))
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    monkeypatch.setenv("STRIPE_PRICE_BUSINESS", "price_biz")
    return TestClient(app)


def _post(client, event):
    payload = json.dumps(event).encode()
    ts = int(time.time())
    sig = hmac.new(b"whsec_test", f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return client.post("/api/v1/billing/webhook", content=payload,
                       headers={"Stripe-Signature": f"t={ts},v1={sig}"})


def _limits(db_path):
    return get_limits(Database(db_path), "org-1")


# ---- B1: checkout must tag the subscription so later events can find the org
def test_checkout_stamps_org_on_subscription(monkeypatch, db_path):
    sent = {}

    class _Resp:
        status_code = 200
        text = ""
        def json(self): return {"url": "https://checkout.stripe.test/x"}

    import requests
    monkeypatch.setattr(requests, "post", lambda url, **kw: sent.update(kw) or _Resp())
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test")
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro")
    monkeypatch.setenv("LEAD_ENGINE_ORG_ID", "org-1")
    monkeypatch.setenv("LEAD_ENGINE_PUBLIC_BASE_URL", "https://x.test")
    c = TestClient(app)
    monkeypatch.setattr(billing_api, "_resolve_org_id", lambda db, req: "org-1")
    monkeypatch.setattr(billing_api, "open_db", lambda: Database(db_path))
    r = c.post("/api/v1/billing/checkout", json={"plan": "pro"})
    assert r.status_code == 200, r.text
    data = sent["data"]
    assert data.get("subscription_data[metadata][org_id]") == "org-1", \
        "subscription is not tagged: cancellation events will have no org"


# ---- B1b: a cancellation event whose subscription carries the org tag downgrades
def test_cancellation_uses_subscription_metadata_stamped_at_checkout(client, db_path):
    db = Database(db_path)
    db.execute("UPDATE organizations SET limits=? WHERE id='org-1'",
               (json.dumps(billing_api.PLANS["pro"]),))
    db.conn.commit(); db.conn.close()
    r = _post(client, {"type": "customer.subscription.deleted",
                       "data": {"object": {"id": "sub_1", "customer": "cus_1",
                                           "metadata": {"org_id": "org-1"}}}})
    assert r.json().get("plan") == "free"
    assert _limits(db_path)["max_jobs_per_day"] == DEFAULT_LIMITS["max_jobs_per_day"]


def test_cancellation_with_no_org_anywhere_is_reported_not_silent(client, caplog):
    """An unattributable cancellation must be LOUD (logged), never a silent skip."""
    import logging
    with caplog.at_level(logging.WARNING):
        r = _post(client, {"type": "customer.subscription.deleted",
                           "data": {"object": {"id": "sub_x", "customer": "cus_x", "metadata": {}}}})
    assert r.status_code == 200 and r.json().get("skipped")
    assert any("unattributed" in rec.getMessage().lower() or "unattributed" in str(getattr(rec, "__dict__", {})).lower()
               for rec in caplog.records), "silent skip of a cancellation"


# ---- B2: never grant more than the price that was actually paid
def test_metadata_plan_cannot_exceed_paid_price(client, db_path):
    r = _post(client, {"type": "checkout.session.completed", "data": {"object": {
        "client_reference_id": "org-1", "customer": "c", "subscription": "s",
        "metadata": {"plan": "business"},
        "line_items": {"data": [{"price": {"id": "price_pro"}}]}}}})
    assert r.status_code == 200
    assert r.json().get("plan") == "pro", f"granted {r.json().get('plan')} for a Pro price"
    assert _limits(db_path)["max_jobs_per_day"] == billing_api.PLANS["pro"]["max_jobs_per_day"]


def test_paid_price_is_fetched_when_event_has_no_line_items(client, db_path, monkeypatch):
    """Real Stripe omits line_items from checkout.session.completed."""
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test")
    calls = []

    class _R:
        status_code = 200
        def json(self): return {"data": [{"price": {"id": "price_pro"}}]}

    import requests
    monkeypatch.setattr(requests, "get", lambda url, **kw: calls.append(url) or _R())
    r = _post(client, {"type": "checkout.session.completed", "data": {"object": {
        "id": "cs_1", "client_reference_id": "org-1", "metadata": {"plan": "business"}}}})
    assert calls and "cs_1/line_items" in calls[0]
    assert r.json().get("plan") == "pro"


def test_stripe_lookup_failure_falls_back_to_metadata_plan(client, monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test")
    import requests
    def boom(*a, **k): raise requests.ConnectionError("down")
    monkeypatch.setattr(requests, "get", boom)
    r = _post(client, {"type": "checkout.session.completed", "data": {"object": {
        "id": "cs_2", "client_reference_id": "org-1", "metadata": {"plan": "pro"}}}})
    assert r.status_code == 200 and r.json().get("plan") == "pro"
