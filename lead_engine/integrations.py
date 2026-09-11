"""OAuth Integration Platform — one platform OAuth app per provider, many
per-tenant connections (public.integration_connections, unique per
organization_id + provider).

Design invariants (docs/architecture.md, Phase 2 "Integration Platform"):
- One registered OAuth application per provider serves ALL customer orgs;
  every org gets its own connection row carrying its own tokens.
- Tokens are never stored in plaintext: access/refresh tokens go through
  lead_engine.secrets.encrypt_secret (AES-GCM, LEAD_ENGINE_ENCRYPTION_KEY)
  into access_token_enc / refresh_token_enc. Plaintext exists only in
  return values, for the caller's request lifetime.
- The OAuth `state` is a signed payload: base64url(JSON) + "." + HMAC-SHA256
  signature over the same encryption key. It carries org_id, provider,
  redirect_uri, a one-shot nonce and an absolute exp — verify_state rejects
  forged, stale, or cross-tenant/cross-provider states in handle_callback.
- Workers never read the token columns directly: they resolve the credential
  at send time via get_valid_access_token(), which transparently refreshes
  when the access token enters the 120s expiry window.

Dialect note: PgDatabase pins search_path=engine, so platform tables in
public.* must be explicitly qualified; SQLite (dev/tests) needs the bare
name. _t() picks the right form from the handle's dialect. All statements
use ? placeholders (the Postgres adapter rewrites them to %s).
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import requests

from .db import utcnow
from .secrets import decrypt_secret, encrypt_secret

STATE_TTL_SECONDS = 600       # signed state is accepted for 10 minutes
REFRESH_WINDOW_SECONDS = 120  # refresh when the access token expires this soon

_TOKEN_TABLE = "integration_connections"

PROVIDERS: dict[str, dict] = {
    "google": {
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "default_scopes": ["openid", "email",
                           "https://www.googleapis.com/auth/gmail.send"],
        "client_id_env": "GOOGLE_CLIENT_ID",
        "client_secret_env": "GOOGLE_CLIENT_SECRET",
        "extra_auth_params": {"access_type": "offline", "prompt": "consent"},
        "enabled": True,
    },
    "hubspot": {
        "auth_url": "https://app.hubspot.com/oauth/authorize",
        "token_url": "https://api.hubapi.com/oauth/v1/token",
        "default_scopes": ["oauth", "crm.objects.contacts.write"],
        "client_id_env": "HUBSPOT_CLIENT_ID",
        "client_secret_env": "HUBSPOT_CLIENT_SECRET",
        "enabled": True,
    },
    "microsoft": {
        "auth_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "default_scopes": ["offline_access", "Mail.Send"],
        "client_id_env": "MS_CLIENT_ID",
        "client_secret_env": "MS_CLIENT_SECRET",
        "enabled": True,
    },
    # Capability-registry entry only: no approved outreach API, so the
    # connect flow must refuse it until an official integration exists.
    "linkedin": {
        "enabled": False,
        "reason": "no approved API for outreach; capability registry",
    },
}


class TokenExchangeError(ValueError):
    """Provider token endpoint rejected the request (or answered unusably)."""


def is_configured(provider: str) -> bool:
    """True when the provider is enabled AND its platform OAuth app
    credentials are present in the environment."""
    spec = PROVIDERS.get(provider)
    if not spec or not spec.get("enabled"):
        return False
    return bool(os.environ.get(spec["client_id_env"])
                and os.environ.get(spec["client_secret_env"]))


# -- dialect helper -----------------------------------------------------------

def _t(db, name: str) -> str:
    """Qualify platform tables for Postgres (search_path is pinned to the
    engine schema, so public.* needs the explicit prefix) and leave the bare
    name for SQLite. Keeps one SQL surface for both backends."""
    return name if getattr(db, "dialect", "sqlite") == "sqlite" else f"public.{name}"


def _scopes_for_db(db, scopes: list[str]):
    """PG text[] wants a real list (psycopg adapts it); SQLite gets JSON text."""
    if getattr(db, "dialect", "sqlite") == "postgres":
        return list(scopes)
    return json.dumps(scopes)


def _parse_scopes(value) -> list[str]:
    """Scopes back to a list. The PG adapter stringifies arrays on read and
    SQLite stores JSON text; a bare string degrades to a single-element list."""
    if not value:
        return []
    if isinstance(value, list):
        return [str(s) for s in value]
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return [str(value)]
    return [str(s) for s in parsed] if isinstance(parsed, list) else [str(parsed)]


def _scopes_from_token(data: dict) -> list[str]:
    """Token endpoints differ: `scope` space/comma separated (Google/MS) or
    `scopes` as a list. Accept both."""
    raw = data.get("scope") or data.get("scopes") or []
    if isinstance(raw, str):
        return [s for s in raw.replace(",", " ").split() if s]
    return [str(s) for s in raw]


def _iso_in(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(value) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
    except ValueError:
        pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


# -- signed state -------------------------------------------------------------

def _hmac_key(raw_key: bytes | None = None) -> bytes:
    """State-signing key: caller-supplied raw key, else the deployment's
    LEAD_ENGINE_ENCRYPTION_KEY (same key material as token encryption)."""
    if raw_key is not None:
        return raw_key
    from .secrets import _key

    return _key()


def encode_state(payload: dict, key: bytes | None = None) -> str:
    """base64url(json payload) + "." + HMAC-SHA256 hex signature."""
    body = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).decode().rstrip("=")
    sig = hmac.new(_hmac_key(key), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def verify_state(state: str, max_age_seconds: int = STATE_TTL_SECONDS,
                 key: bytes | None = None) -> dict:
    """Decode + authenticate a state token. Returns the payload dict.

    Raises ValueError on malformed input, signature mismatch, or age: the
    payload's absolute `exp` (issued + STATE_TTL_SECONDS) recovers the
    issuance time, and states older than max_age_seconds are rejected."""
    if not state or "." not in state:
        raise ValueError("malformed state")
    body, _, sig = state.rpartition(".")
    expected = hmac.new(_hmac_key(key), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise ValueError("state signature mismatch")
    pad = "=" * (-len(body) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(body + pad))
    except (TypeError, ValueError) as exc:
        raise ValueError("state payload not decodable") from exc
    if not isinstance(payload, dict):
        raise ValueError("state payload not a dict")
    issued_at = float(payload.get("exp") or 0) - STATE_TTL_SECONDS
    if time.time() - issued_at > max_age_seconds:
        raise ValueError("state expired")
    return payload


# -- connect / callback --------------------------------------------------------

def build_authorization_url(db, org_id: str, provider: str,
                            redirect_uri: str) -> tuple[str, str]:
    """Start the OAuth code flow for one org+provider.

    Creates (or resets to 'pending') the connection row, signs a state bound
    to this org/provider/redirect_uri, and returns (authorize_url, state).
    Raises ValueError when the provider is unknown or not configured."""
    spec = PROVIDERS.get(provider)
    if spec is None:
        raise ValueError(f"unknown provider: {provider}")
    if not is_configured(provider):
        raise ValueError(f"provider not configured or disabled: {provider}")

    state = encode_state({
        "org_id": org_id,
        "provider": provider,
        "redirect_uri": redirect_uri,
        "nonce": secrets.token_urlsafe(16),
        "exp": time.time() + STATE_TTL_SECONDS,
    })
    table = _t(db, _TOKEN_TABLE)
    now = utcnow()
    db.execute(
        f"INSERT INTO {table} (organization_id, provider, status, created_at,"
        f" updated_at) VALUES (?,?,'pending',?,?)"
        f" ON CONFLICT (organization_id, provider) DO UPDATE SET"
        f" status = 'pending', updated_at = excluded.updated_at",
        (org_id, provider, now, now))

    params = {
        "client_id": os.environ[spec["client_id_env"]],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(spec["default_scopes"]),
        "state": state,
    }
    params.update(spec.get("extra_auth_params") or {})
    return f"{spec['auth_url']}?{urlencode(params)}", state


def _exchange_error(resp) -> str:
    """Best-effort human-readable provider error (never includes tokens)."""
    try:
        data = resp.json()
    except (TypeError, ValueError):
        return f"HTTP {getattr(resp, 'status_code', '?')}"
    detail = data.get("error_description") or data.get("error") or getattr(resp, "text", "")
    return f"HTTP {resp.status_code}: {str(detail)[:300]}"


def _post_token_form(spec: dict, form: dict) -> dict:
    """POST form-encoded credentials to the provider token endpoint and
    return the parsed JSON, raising TokenExchangeError on any failure."""
    resp = requests.post(spec["token_url"], data=form, timeout=30)
    if resp.status_code != 200:
        raise TokenExchangeError(_exchange_error(resp))
    try:
        data = resp.json()
    except (TypeError, ValueError) as exc:
        raise TokenExchangeError("invalid JSON from token endpoint") from exc
    if not data.get("access_token"):
        detail = data.get("error_description") or data.get("error") \
            or "missing access_token"
        raise TokenExchangeError(str(detail)[:300])
    return data


def _mark_error(db, org_id: str, provider: str, message: str) -> None:
    table = _t(db, _TOKEN_TABLE)
    now = utcnow()
    db.execute(
        f"INSERT INTO {table} (organization_id, provider, status, last_error,"
        f" created_at, updated_at) VALUES (?,?,'error',?,?,?)"
        f" ON CONFLICT (organization_id, provider) DO UPDATE SET"
        f" status = 'error', last_error = excluded.last_error,"
        f" updated_at = excluded.updated_at",
        (org_id, provider, message[:500], now, now))


def handle_callback(db, org_id: str, provider: str, code: str, state: str,
                    redirect_uri: str | None = None) -> dict:
    """Finish the OAuth code flow: verify the signed state, exchange the code
    at the provider token endpoint, and store the tokens AES-GCM encrypted.

    State policy: verify_state() must succeed AND its payload must match this
    org/provider — cross-tenant or cross-provider replays are rejected.

    Error policy: on any token-endpoint failure the connection row is flipped
    to status='error' with last_error, then ValueError is raised (the API
    layer maps it to HTTP 400). Success returns a sanitized connection dict.

    redirect_uri defaults to the one bound into the state (providers require
    it to match the authorize request)."""
    spec = PROVIDERS.get(provider)
    if spec is None:
        raise ValueError(f"unknown provider: {provider}")
    payload = verify_state(state)
    if payload.get("org_id") != org_id or payload.get("provider") != provider:
        raise ValueError("state does not match this org/provider")
    redirect = redirect_uri or payload.get("redirect_uri") or ""

    try:
        data = _post_token_form(spec, {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect,
            "client_id": os.environ.get(spec["client_id_env"], ""),
            "client_secret": os.environ.get(spec["client_secret_env"], ""),
        })
    except TokenExchangeError as exc:
        _mark_error(db, org_id, provider, str(exc))
        raise ValueError(f"{provider} token exchange failed: {exc}") from exc

    scopes = _scopes_from_token(data)
    expires_at = _iso_in(int(data.get("expires_in") or 3600))
    now = utcnow()
    refresh = data.get("refresh_token")
    table = _t(db, _TOKEN_TABLE)
    db.execute(
        f"INSERT INTO {table} (organization_id, provider, status, scopes,"
        f" access_token_enc, refresh_token_enc, expires_at, last_refresh_at,"
        f" last_error, created_at, updated_at)"
        f" VALUES (?,?,?,?,?,?,?,?,NULL,?,?)"
        f" ON CONFLICT (organization_id, provider) DO UPDATE SET"
        f" status = 'connected', scopes = excluded.scopes,"
        f" access_token_enc = excluded.access_token_enc,"
        f" refresh_token_enc = excluded.refresh_token_enc,"
        f" expires_at = excluded.expires_at,"
        f" last_refresh_at = excluded.last_refresh_at, last_error = NULL,"
        f" updated_at = excluded.updated_at",
        (org_id, provider, "connected", _scopes_for_db(db, scopes),
         encrypt_secret(str(data["access_token"])),
         encrypt_secret(refresh) if refresh else None,
         expires_at, now, now, now))
    return {"provider": provider, "status": "connected", "scopes": scopes,
            "expires_at": expires_at, "last_refresh_at": now}


# -- send-time resolution ------------------------------------------------------

def _load_connection(db, org_id: str, provider: str) -> dict | None:
    table = _t(db, _TOKEN_TABLE)
    return db.one(
        f"SELECT * FROM {table} WHERE organization_id = ? AND provider = ?",
        (org_id, provider))


def get_connection(db, org_id: str, provider: str) -> dict | None:
    """Sanitized connection view — never returns token ciphertext."""
    row = _load_connection(db, org_id, provider)
    if not row:
        return None
    return {
        "provider": row.get("provider"),
        "status": row.get("status"),
        "scopes": _parse_scopes(row.get("scopes")),
        "expires_at": row.get("expires_at"),
        "last_refresh_at": row.get("last_refresh_at"),
        "last_error": row.get("last_error"),
    }


def connections_for_org(db, org_id: str) -> dict[str, dict]:
    """{provider: sanitized connection} for every stored row of the org."""
    table = _t(db, _TOKEN_TABLE)
    rows = db.query(
        f"SELECT provider, status, scopes, expires_at, last_refresh_at,"
        f" last_error FROM {table} WHERE organization_id = ?", (org_id,))
    return {r["provider"]: {
        "status": r["status"],
        "scopes": _parse_scopes(r["scopes"]),
        "expires_at": r["expires_at"],
        "last_refresh_at": r["last_refresh_at"],
        "last_error": r["last_error"],
    } for r in rows}


def get_valid_access_token(db, org_id: str, provider: str) -> str:
    """Credential-at-send-time resolution for workers: decrypt the stored
    access token; when it is inside the 120s expiry window and a refresh
    token exists, refresh it via the provider token endpoint first (updating
    the encrypted columns).

    Raises ConnectionError('not connected') when no connected row exists.
    A failed refresh records last_error but keeps status='connected'
    (transient provider errors must not force re-consent) and raises
    ConnectionError. Without a refresh token the current token is returned."""
    spec = PROVIDERS.get(provider)
    if spec is None:
        raise ValueError(f"unknown provider: {provider}")
    row = _load_connection(db, org_id, provider)
    if not row or row.get("status") != "connected" \
            or not row.get("access_token_enc"):
        raise ConnectionError("not connected")
    token = decrypt_secret(row["access_token_enc"])

    expires_at = _parse_iso(row.get("expires_at"))
    seconds_left = ((expires_at - datetime.now(timezone.utc)).total_seconds()
                    if expires_at else 0)
    if seconds_left > REFRESH_WINDOW_SECONDS:
        return token
    refresh_enc = row.get("refresh_token_enc")
    if not refresh_enc:
        return token

    try:
        data = _post_token_form(spec, {
            "grant_type": "refresh_token",
            "refresh_token": decrypt_secret(refresh_enc),
            "client_id": os.environ.get(spec["client_id_env"], ""),
            "client_secret": os.environ.get(spec["client_secret_env"], ""),
        })
    except TokenExchangeError as exc:
        table = _t(db, _TOKEN_TABLE)
        db.execute(
            f"UPDATE {table} SET last_error = ?, updated_at = ?"
            f" WHERE organization_id = ? AND provider = ?",
            (str(exc)[:500], utcnow(), org_id, provider))
        raise ConnectionError(f"token refresh failed: {exc}") from exc

    now = utcnow()
    new_refresh = data.get("refresh_token")
    table = _t(db, _TOKEN_TABLE)
    db.execute(
        f"UPDATE {table} SET access_token_enc = ?,"
        f" refresh_token_enc = COALESCE(?, refresh_token_enc),"
        f" expires_at = ?, last_refresh_at = ?, last_error = NULL, updated_at = ?"
        f" WHERE organization_id = ? AND provider = ?",
        (encrypt_secret(str(data["access_token"])),
         encrypt_secret(new_refresh) if new_refresh else None,
         _iso_in(int(data.get("expires_in") or 3600)), now, now,
         org_id, provider))
    return str(data["access_token"])


def revoke_connection(db, org_id: str, provider: str) -> dict | None:
    """Revoke the org's connection: status='revoked', token columns cleared.
    Returns the sanitized connection dict, or None when nothing was stored."""
    table = _t(db, _TOKEN_TABLE)
    cur = db.execute(
        f"UPDATE {table} SET status = 'revoked', access_token_enc = NULL,"
        f" refresh_token_enc = NULL, expires_at = NULL, updated_at = ?"
        f" WHERE organization_id = ? AND provider = ?",
        (utcnow(), org_id, provider))
    if cur.rowcount == 0:
        return None
    return get_connection(db, org_id, provider)
