"""Small cookie-based admin session for the control plane.

The password and signing secret stay server-side. The browser only receives an
HttpOnly, signed session cookie; no admin credential is bundled into the SPA.
"""
import hashlib
import hmac
import os
import time

COOKIE_NAME = "lead_engine_session"
SESSION_TTL_SECONDS = 60 * 60 * 12


def enabled() -> bool:
    return bool(os.environ.get("LEAD_ENGINE_ADMIN_PASSWORD"))


def _secret() -> bytes:
    return (os.environ.get("LEAD_ENGINE_AUTH_SECRET") or
            os.environ.get("LEAD_ENGINE_ADMIN_PASSWORD", "dev-only-secret")).encode()


def issue_session() -> str:
    expires = str(int(time.time()) + SESSION_TTL_SECONDS)
    signature = hmac.new(_secret(), expires.encode(), hashlib.sha256).hexdigest()
    return f"{expires}.{signature}"


def valid_session(value: str | None) -> bool:
    if not enabled() or not value or "." not in value:
        return not enabled()
    expires, signature = value.split(".", 1)
    if not expires.isdigit() or int(expires) < int(time.time()):
        return False
    expected = hmac.new(_secret(), expires.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


def password_matches(password: str) -> bool:
    configured = os.environ.get("LEAD_ENGINE_ADMIN_PASSWORD", "").encode()
    return bool(configured) and hmac.compare_digest(password.encode(), configured)
