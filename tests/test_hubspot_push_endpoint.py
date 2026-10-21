"""POST /api/v1/integrations/hubspot/push-leads: safety contract end to end
(real SQLite, no network)."""
import base64
import secrets as pysecrets

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from lead_engine import integrations
from lead_engine.db import Database
from tests.test_integrations import CONNECTIONS_DDL

SUPPRESSION_DDL = """CREATE TABLE IF NOT EXISTS suppression_entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT, organization_id TEXT, channel TEXT,
  value TEXT, reason TEXT, source TEXT, created_at TEXT)"""
ORG, OTHER = "org-a", "org-b"
URL = "/api/v1/integrations/hubspot/push-leads"


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("LEAD_ENGINE_ENCRYPTION_KEY",
                       base64.urlsafe_b64encode(pysecrets.token_bytes(32)).decode())
    monkeypatch.setenv("LEAD_ENGINE_ORG_ID", ORG)
    d = Database(tmp_path / "push.sqlite3")
    d.execute(CONNECTIONS_DDL)
    d.execute(SUPPRESSION_DDL)
    d.org_id = ORG
    yield d
    d.conn.close()


def _lead(db, org, name, email, **kw):
    db.org_id = org
    row = {"name": name, "domain": f"{name.lower().replace(' ', '')}.sa",
           "email": email, "email_status": "DELIVERABLE", "stage": "ACCEPTED",
           "legal_decision": "ACCEPTED", "score": 80, "job_id": "j1"}
    row.update(kw)
    db.insert_lead(row)
    db.org_id = ORG


@pytest.fixture
def api(db, monkeypatch):
    from lead_engine.api import integrations_api as ia

    def override():
        yield db
    app = FastAPI()
    app.include_router(ia.router)
    app.dependency_overrides[ia.get_db] = override
    posts = []

    class R:
        status_code = 200
        text = ""
    monkeypatch.setattr(ia.requests, "post",
                        lambda url, **k: (posts.append((url, k)), R())[1])
    client = TestClient(app)
    client.posts = posts
    return client


def _connect(db):
    ok = integrations.encrypt_secret("hs-token")
    db.execute(
        "INSERT INTO integration_connections (organization_id, provider, status,"
        " access_token_enc, expires_at) VALUES (?,?,?,?,?)",
        (ORG, "hubspot", "connected", ok, "2999-01-01T00:00:00+00:00"))


def test_defaults_to_dry_run_and_sends_nothing(api, db):
    _lead(db, ORG, "Smile Dental", "a@smile.sa")
    r = api.post(URL)
    assert r.status_code == 200
    body = r.json()
    assert body["dry_run"] is True and body["eligible"] == 1 and body["pushed"] == 0
    assert api.posts == []


def test_dry_run_works_even_when_hubspot_not_connected(api, db):
    _lead(db, ORG, "Smile Dental", "a@smile.sa")
    assert api.post(URL).status_code == 200


def test_real_push_without_connection_is_409_and_sends_nothing(api, db):
    _lead(db, ORG, "Smile Dental", "a@smile.sa")
    r = api.post(URL, params={"dry_run": "false"})
    assert r.status_code == 409
    assert api.posts == []


def test_real_push_sends_to_hubspot_and_writes_audit_without_pii(api, db):
    _connect(db)
    _lead(db, ORG, "Smile Dental", "a@smile.sa")
    r = api.post(URL, params={"dry_run": "false"})
    assert r.status_code == 200 and r.json()["pushed"] == 1
    url, kw = api.posts[0]
    assert url == "https://api.hubapi.com/crm/v3/objects/contacts/batch/upsert"
    assert kw["headers"]["Authorization"] == "Bearer hs-token"
    assert kw["json"]["inputs"][0]["id"] == "a@smile.sa"
    rows = db.query("SELECT action, payload_json FROM audit_logs"
                    " WHERE action = 'crm.hubspot.push'")
    assert len(rows) == 1
    assert "a@smile.sa" not in rows[0]["payload_json"]
    assert "hs-token" not in rows[0]["payload_json"]


def test_other_tenants_leads_are_never_pushed(api, db):
    _connect(db)
    _lead(db, ORG, "Mine Clinic", "mine@mine.sa")
    _lead(db, OTHER, "Theirs Clinic", "theirs@theirs.sa")
    r = api.post(URL, params={"dry_run": "false"})
    sent = [i["id"] for _, k in api.posts for i in k["json"]["inputs"]]
    assert sent == ["mine@mine.sa"] and r.json()["pushed"] == 1


def test_suppressed_erased_rejected_and_review_leads_are_skipped(api, db):
    from lead_engine.policy import Suppression
    _connect(db)
    _lead(db, ORG, "Good One", "good@good.sa")
    _lead(db, ORG, "Unsub", "unsub@unsub.sa")
    _lead(db, ORG, "Erased", "erased@erased.sa", legal_decision="retention-erased")
    _lead(db, ORG, "Rejected", "rej@rej.sa", disposition="REJECT")
    _lead(db, ORG, "InReview", "rev@rev.sa", stage="REVIEW")
    Suppression.add(db, ORG, "email", "unsub@unsub.sa", "unsubscribed")
    r = api.post(URL, params={"dry_run": "false"})
    sent = [i["id"] for _, k in api.posts for i in k["json"]["inputs"]]
    assert sent == ["good@good.sa"]
    assert r.json()["skipped_by_reason"] == {"suppressed": 1, "retention_erased": 1,
                                             "reviewer_rejected": 1}


def test_limit_is_bounded(api):
    assert api.post(URL, params={"limit": 0}).status_code == 422
    assert api.post(URL, params={"limit": 2001}).status_code == 422


def test_machine_token_is_forbidden(db, monkeypatch):
    from lead_engine.api import integrations_api as ia
    app = FastAPI()

    @app.middleware("http")
    async def machine(request, call_next):
        request.state.machine = True
        request.state.claims = None
        return await call_next(request)
    app.include_router(ia.router)

    def override():
        yield db
    app.dependency_overrides[ia.get_db] = override
    r = TestClient(app).post(URL)
    assert r.status_code == 403


def test_fails_closed_when_suppression_list_is_unreadable(db, api):
    """No suppression table (as on a bare SQLite): refuse, never push blind."""
    _connect(db)
    _lead(db, ORG, "Smile Dental", "a@smile.sa")
    db.execute("DROP TABLE suppression_entries")
    for dry in ("true", "false"):
        r = api.post(URL, params={"dry_run": dry})
        assert r.status_code == 503, dry
    assert api.posts == []
