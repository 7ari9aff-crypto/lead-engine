"""Supabase Auth JWT validation for the control plane.

Resolution order per request (middleware in app.py):
1. `Authorization: Bearer <supabase-jwt>` — validated against the project
   JWKS (asymmetric signing) or SUPABASE_JWT_SECRET (legacy HS256 projects).
2. Legacy signed-cookie session (auth.valid_session) — local dev and the
   existing dashboard password flow.
3. When neither auth mechanism is configured (local dev), the plane is open.

Tenant context: claims["sub"] resolves the active organization through
organization_members; LEAD_ENGINE_ORG_ID stays the single-org bridge while
the runtime is single-tenant (Phase 1).
"""
import os
import time
from functools import lru_cache

import jwt
import requests

_JWKS_URL = "/auth/v1/.well-known/jwks.json"


def supabase_url() -> str | None:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    return url or None


@lru_cache(maxsize=1)
def _jwks_client() -> jwt.PyJWKClient | None:
    url = supabase_url()
    if not url:
        return None
    return jwt.PyJWKClient(url + _JWKS_URL, cache_keys=True, lifespan=3600)


def validate_supabase_jwt(token: str) -> dict | None:
    """Return claims for a valid Supabase access token, else None.

    Never raises: an invalid/expired/foreign token is simply 'not a session'.
    """
    if not token:
        return None
    secret = os.environ.get("SUPABASE_JWT_SECRET")
    try:
        if secret:
            return jwt.decode(token, secret, algorithms=["HS256"],
                              audience="authenticated")
        client = _jwks_client()
        if client is None:
            return None
        signing_key = client.get_signing_key_from_jwt(token)
        return jwt.decode(
            token, signing_key.key, algorithms=["ES256", "RS256", "EdDSA"],
            audience="authenticated")
    except Exception:
        return None


def bearer_token(request_headers) -> str | None:
    auth = request_headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        return token or None
    return None


def resolve_org_id(claims: dict, db) -> str | None:
    """Active organization for the token subject (first membership)."""
    sub = (claims or {}).get("sub")
    if not sub or not claims.get("email"):
        # anonymous/mobile tokens carry no email — still allow sub lookup
        sub = sub or (claims or {}).get("sub")
    if not sub:
        return None
    try:
        row = db.one(
            "SELECT organization_id FROM public.organization_members WHERE user_id = ?"
            " ORDER BY created_at LIMIT 1", (sub,))
    except Exception:
        return None
    return row["organization_id"] if row else None


def auth_mode() -> str:
    """Which login surface the dashboard should show."""
    if supabase_url():
        return "supabase"
    if os.environ.get("LEAD_ENGINE_ADMIN_PASSWORD"):
        return "password"
    return "open"


def token_expired(claims: dict) -> bool:
    exp = (claims or {}).get("exp")
    return bool(exp and int(exp) < int(time.time()))
