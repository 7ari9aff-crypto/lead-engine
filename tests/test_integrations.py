"""OAuth Integration Platform: signed state round-trip, encrypted token
storage on callback, send-time resolution with refresh, revocation — plus the
FastAPI router. SQLite backend with the token endpoint mocked.

The public.integration_connections table is mirrored in SQLite under the bare
name `integration_connections` (see integrations._t): same columns, TEXT ids,
UNIQUE (organization_id, provider) so the module's ON CONFLICT upserts work.
"""
import base64
import secrets as pysecrets
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from lead_engine import integrations
from lead_engine.db import Database
from lead_engine.secrets import decrypt_secret

ORG = "org-test-1234"

CONNECTIONS_DDL = """
CREATE TABLE IF NOT EXISTS integration_connections (
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  organization_id TEXT,
  provider TEXT,
  status TEXT DEFAULT 'pending',
  scopes TEXT DEFAULT '[]',
  provider_account_id TEXT,
  provider_account_email TEXT,
  access_token_enc TEXT,
  refresh_token_enc TEXT,
  expires_at TEXT,
  last_refresh_at TEXT,
  last_error TEXT,
  created_at TEXT,
  updated_at TEXT,
  UNIQUE (organization_id, provider)
)
"""


@pytest.fixture
def db(tmp_path, monkeypatch):
    # fresh encryption key per test — key material never crosses tests
    monkeypatch.setenv("LEAD_ENGINE_ENCRYPTION_KEY",
                       base64.urlsafe_b64encode(pysecrets.token_bytes(32)).decode())
    database = Database(tmp_path / "integrations.sqlite3")
    database.execute(CONNECTIONS_DDL)
    yield database
    database.conn.close()


def _google_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-google-secret")


class FakeTokenResponse:
    def __init__(self, status_code=200, payload=None, text="provider error"):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


def _fake_token_post(calls, payload=None, status_code=200):
    def fake_post(url, data=None, timeout=None):
        calls.append({"url": url, "data": dict(data or {})})
        return FakeTokenResponse(status_code=status_code, payload=payload or {})
    return fake_post


def _connect(db, monkeypatch, expires_in=3600):
    """Drive build_authorization_url + handle_callback with a mocked token
    endpoint so a connected row exists for the resolution/revocation tests."""
    _google_env(monkeypatch)
    _, state = integrations.build_authorization_url(db, ORG, "google",
                                                    "https://app.example/cb")
    monkeypatch.setattr(integrations.requests, "post", _fake_token_post(
        [], {"access_token": "AT-PLAIN-123", "refresh_token": "RT-PLAIN-456",
             "expires_in": expires_in, "scope": "openid email"}))
    integrations.handle_callback(db, ORG, "google", "AUTHCODE", state)


# -- signed state ----------------------------------------------------------------

def test_state_sign_verify_round_trip(db, monkeypatch):
    _google_env(monkeypatch)
    url, state = integrations.build_authorization_url(db, ORG, "google",
                                                      "https://app.example/cb")
    payload = integrations.verify_state(state)
    assert payload["org_id"] == ORG
    assert payload["provider"] == "google"
    assert payload["redirect_uri"] == "https://app.example/cb"
    assert payload["nonce"]  # one-shot value present
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")


def test_state_expired_rejected():
    key = pysecrets.token_bytes(32)  # raw-key path, no env key needed
    stale = integrations.encode_state({
        "org_id": ORG, "provider": "google", "redirect_uri": "https://app.example/cb",
        "nonce": "n1", "exp": time.time() - 10_000,
    }, key=key)
    with pytest.raises(ValueError, match="expired"):
        integrations.verify_state(stale, key=key)


def test_state_tampered_rejected(db, monkeypatch):
    _google_env(monkeypatch)
    _, state = integrations.build_authorization_url(db, ORG, "google",
                                                    "https://app.example/cb")
    body, sig = state.rsplit(".", 1)
    tampered_body = body[:-1] + ("A" if body[-1] != "A" else "B")
    with pytest.raises(ValueError, match="signature"):
        integrations.verify_state(f"{tampered_body}.{sig}")
    bad_sig = sig[:-1] + ("0" if sig[-1] != "0" else "1")
    with pytest.raises(ValueError, match="signature"):
        integrations.verify_state(f"{body}.{bad_sig}")


def test_state_malformed_rejected():
    with pytest.raises(ValueError):
        integrations.verify_state("")
    with pytest.raises(ValueError):
        integrations.verify_state("not-a-signed-state")


# -- build_authorization_url -------------------------------------------------------

def test_build_url_contains_oauth_params_and_pending_row(db, monkeypatch):
    _google_env(monkeypatch)
    url, state = integrations.build_authorization_url(db, ORG, "google",
                                                      "https://app.example/cb")
    for piece in ("client_id=test-google-client", "response_type=code",
                  "scope=openid+email+https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fgmail.send",
                  "access_type=offline", "prompt=consent", "state="):
        assert piece in url
    row = db.one("SELECT status FROM integration_connections"
                 " WHERE organization_id = ? AND provider = ?", (ORG, "google"))
    assert row and row["status"] == "pending"


def test_build_url_not_configured_raises(db, monkeypatch):
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    with pytest.raises(ValueError, match="not configured"):
        integrations.build_authorization_url(db, ORG, "google", "https://app.example/cb")


def test_build_url_unknown_provider_raises(db):
    with pytest.raises(ValueError, match="unknown provider"):
        integrations.build_authorization_url(db, ORG, "notaprovider",
                                             "https://app.example/cb")


def test_linkedin_is_capability_registry_only(db):
    assert integrations.PROVIDERS["linkedin"]["enabled"] is False
    assert integrations.is_configured("linkedin") is False


# -- handle_callback -----------------------------------------------------------------

def test_handle_callback_stores_encrypted_tokens(db, monkeypatch):
    _google_env(monkeypatch)
    _, state = integrations.build_authorization_url(db, ORG, "google",
                                                    "https://app.example/cb")
    calls = []
    monkeypatch.setattr(integrations.requests, "post", _fake_token_post(
        calls, {"access_token": "AT-PLAIN-123", "refresh_token": "RT-PLAIN-456",
                "expires_in": 3600, "scope": "openid email"}))
    result = integrations.handle_callback(db, ORG, "google", "AUTHCODE", state)

    assert result["status"] == "connected"
    assert result["scopes"] == ["openid", "email"]
    assert result["expires_at"] and result["last_refresh_at"]
    row = db.one("SELECT * FROM integration_connections"
                 " WHERE organization_id = ? AND provider = ?", (ORG, "google"))
    assert row["status"] == "connected"
    # ciphertext in the row, never plaintext
    assert row["access_token_enc"] != "AT-PLAIN-123"
    assert row["refresh_token_enc"] != "RT-PLAIN-456"
    assert "AT-PLAIN-123" not in str(row)
    assert decrypt_secret(row["access_token_enc"]) == "AT-PLAIN-123"
    assert decrypt_secret(row["refresh_token_enc"]) == "RT-PLAIN-456"
    assert row["last_error"] is None
    # the code exchange hit the token endpoint with the form-encoded grant
    assert calls[0]["url"] == "https://oauth2.googleapis.com/token"
    assert calls[0]["data"]["grant_type"] == "authorization_code"
    assert calls[0]["data"]["code"] == "AUTHCODE"
    assert calls[0]["data"]["client_id"] == "test-google-client"
    assert calls[0]["data"]["redirect_uri"] == "https://app.example/cb"


def test_handle_callback_provider_error_marks_row_and_raises(db, monkeypatch):
    _google_env(monkeypatch)
    _, state = integrations.build_authorization_url(db, ORG, "google",
                                                    "https://app.example/cb")
    monkeypatch.setattr(integrations.requests, "post", _fake_token_post(
        [], {"error": "invalid_grant",
             "error_description": "code was already redeemed"}, status_code=400))
    with pytest.raises(ValueError, match="code was already redeemed"):
        integrations.handle_callback(db, ORG, "google", "BAD", state)
    row = db.one("SELECT status, last_error FROM integration_connections"
                 " WHERE organization_id = ? AND provider = ?", (ORG, "google"))
    assert row["status"] == "error"
    assert "code was already redeemed" in row["last_error"]


def test_handle_callback_rejects_state_mismatch(db, monkeypatch):
    _google_env(monkeypatch)
    _, state = integrations.build_authorization_url(db, ORG, "google",
                                                    "https://app.example/cb")
    calls = []
    monkeypatch.setattr(integrations.requests, "post", _fake_token_post(calls, {}))
    with pytest.raises(ValueError, match="does not match"):
        integrations.handle_callback(db, "org-OTHER", "google", "AUTHCODE", state)
    with pytest.raises(ValueError, match="does not match"):
        integrations.handle_callback(db, ORG, "hubspot", "AUTHCODE", state)
    assert calls == []  # token endpoint never reached


# -- get_valid_access_token ------------------------------------------------------------

def test_get_token_far_from_expiry_skips_refresh(db, monkeypatch):
    _connect(db, monkeypatch, expires_in=3600)

    def _must_not_post(url, data=None, timeout=None):
        raise AssertionError("token endpoint must not be called")

    monkeypatch.setattr(integrations.requests, "post", _must_not_post)
    assert integrations.get_valid_access_token(db, ORG, "google") == "AT-PLAIN-123"


def test_get_token_refreshes_near_expiry(db, monkeypatch):
    _connect(db, monkeypatch, expires_in=3600)
    # force the access token inside the 120s refresh window
    db.execute("UPDATE integration_connections SET expires_at = ?"
               " WHERE organization_id = ? AND provider = ?",
               (integrations._iso_in(30), ORG, "google"))
    calls = []
    monkeypatch.setattr(integrations.requests, "post", _fake_token_post(
        calls, {"access_token": "AT-NEW-789", "expires_in": 3600}))
    token = integrations.get_valid_access_token(db, ORG, "google")
    assert token == "AT-NEW-789"
    assert calls[0]["data"]["grant_type"] == "refresh_token"
    assert calls[0]["data"]["refresh_token"] == "RT-PLAIN-456"
    row = db.one("SELECT access_token_enc, refresh_token_enc FROM integration_connections"
                 " WHERE organization_id = ? AND provider = ?", (ORG, "google"))
    assert decrypt_secret(row["access_token_enc"]) == "AT-NEW-789"
    # provider kept the old refresh token -> the row keeps it too (COALESCE)
    assert decrypt_secret(row["refresh_token_enc"]) == "RT-PLAIN-456"


def test_get_token_without_connection_raises(db, monkeypatch):
    with pytest.raises(ConnectionError, match="not connected"):
        integrations.get_valid_access_token(db, ORG, "google")


def test_get_token_after_revoke_raises(db, monkeypatch):
    _connect(db, monkeypatch)
    db.execute("UPDATE integration_connections SET status = 'connected',"
               " access_token_enc = NULL WHERE organization_id = ? AND provider = ?",
               (ORG, "google"))
    with pytest.raises(ConnectionError, match="not connected"):
        integrations.get_valid_access_token(db, ORG, "google")


# -- revoke -----------------------------------------------------------------------------

def test_revoke_clears_tokens(db, monkeypatch):
    _connect(db, monkeypatch)
    result = integrations.revoke_connection(db, ORG, "google")
    assert result["status"] == "revoked"
    row = db.one("SELECT status, access_token_enc, refresh_token_enc, expires_at"
                 " FROM integration_connections"
                 " WHERE organization_id = ? AND provider = ?", (ORG, "google"))
    assert row["status"] == "revoked"
    assert row["access_token_enc"] is None
    assert row["refresh_token_enc"] is None
    assert row["expires_at"] is None
    with pytest.raises(ConnectionError, match="not connected"):
        integrations.get_valid_access_token(db, ORG, "google")


def test_revoke_without_row_returns_none(db):
    assert integrations.revoke_connection(db, ORG, "google") is None


# -- FastAPI router -----------------------------------------------------------------------

@pytest.fixture
def api(db, monkeypatch):
    monkeypatch.setenv("LEAD_ENGINE_ORG_ID", ORG)
    from lead_engine.api import integrations_api

    def override_get_db():
        yield db

    app = FastAPI()
    app.include_router(integrations_api.router)
    app.dependency_overrides[integrations_api.get_db] = override_get_db
    return TestClient(app)


def test_list_integrations_covers_registry(api):
    body = api.get("/api/v1/integrations")
    assert body.status_code == 200
    entries = body.json()["integrations"]
    assert [e["provider"] for e in entries] == ["google", "hubspot",
                                                "microsoft", "linkedin"]
    linkedin = entries[-1]
    assert linkedin["configured"] is False
    assert linkedin["connected"] is False
    assert linkedin["status"] == "not_connected"
    google = entries[0]
    assert google["configured"] is False  # no creds in this test's env
    assert google["scopes"] == []


def test_connect_endpoint_builds_url_and_pending_row(api, db, monkeypatch):
    _google_env(monkeypatch)
    r = api.post("/api/v1/integrations/google/connect",
                 params={"redirect_uri": "https://app.example/cb"})
    assert r.status_code == 200
    body = r.json()
    assert body["authorize_url"].startswith(
        "https://accounts.google.com/o/oauth2/v2/auth")
    assert "state=" in body["authorize_url"]
    integrations.verify_state(body["state"])  # same-key round trip
    row = db.one("SELECT status FROM integration_connections"
                 " WHERE organization_id = ? AND provider = ?", (ORG, "google"))
    assert row["status"] == "pending"


def test_connect_endpoint_409_when_not_configured(api, monkeypatch):
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    r = api.post("/api/v1/integrations/google/connect",
                 params={"redirect_uri": "https://app.example/cb"})
    assert r.status_code == 409


def test_connect_endpoint_409_for_disabled_provider(api):
    r = api.post("/api/v1/integrations/linkedin/connect",
                 params={"redirect_uri": "https://app.example/cb"})
    assert r.status_code == 409


def test_connect_endpoint_404_unknown_provider(api):
    r = api.post("/api/v1/integrations/notaprovider/connect")
    assert r.status_code == 404


def test_callback_endpoint_connects(api, db, monkeypatch):
    _google_env(monkeypatch)
    _, state = integrations.build_authorization_url(db, ORG, "google",
                                                    "https://app.example/cb")
    monkeypatch.setattr(integrations.requests, "post", _fake_token_post(
        [], {"access_token": "AT-1", "refresh_token": "RT-1",
             "expires_in": 3600, "scope": "openid email"}))
    r = api.get("/api/v1/integrations/google/callback",
                params={"code": "AUTHCODE", "state": state})
    assert r.status_code == 200
    assert r.json() == {"connected": True, "provider": "google"}
    row = db.one("SELECT status FROM integration_connections"
                 " WHERE organization_id = ? AND provider = ?", (ORG, "google"))
    assert row["status"] == "connected"


def test_callback_endpoint_400_on_bad_state(api):
    r = api.get("/api/v1/integrations/google/callback",
                params={"code": "AUTHCODE", "state": "forged.junk"})
    assert r.status_code == 400


def test_revoke_endpoint_marks_revoked(api, db, monkeypatch):
    _connect(db, monkeypatch)
    r = api.post("/api/v1/integrations/google/revoke")
    assert r.status_code == 200
    assert r.json()["status"] == "revoked"
    listed = api.get("/api/v1/integrations").json()["integrations"]
    google = next(e for e in listed if e["provider"] == "google")
    assert google["connected"] is False
    assert google["status"] == "revoked"


def test_revoke_endpoint_404_without_connection(api):
    r = api.post("/api/v1/integrations/google/revoke")
    assert r.status_code == 404
