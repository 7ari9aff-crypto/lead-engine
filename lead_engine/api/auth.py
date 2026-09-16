"""Small cookie-based admin session for the control plane.

The password and signing secret stay server-side. The browser only receives an
HttpOnly, signed session cookie; no admin credential is bundled into the SPA.
"""
import hashlib
import hmac
import os
import threading
import time

COOKIE_NAME = "lead_engine_session"
SESSION_TTL_SECONDS = 60 * 60 * 12

# Process-local throttling is intentional: login is a legacy, single-process
# endpoint and must not require Redis or another external service. Keys contain
# only the client address; passwords and secrets are never retained or logged.
_LOGIN_LOCK = threading.Lock()
_LOGIN_ATTEMPTS: dict[str, tuple[int, float]] = {}
_LOGIN_MAX_FAILURES = 5
_LOGIN_BACKOFF_SECONDS = (1, 2, 5, 15, 30, 60)
_LOGIN_STATE_TTL_SECONDS = 60 * 60


def login_retry_after(client_key: str, now: float | None = None) -> int:
    """Return remaining lockout seconds, or zero when login may proceed."""
    current = time.time() if now is None else now
    with _LOGIN_LOCK:
        state = _LOGIN_ATTEMPTS.get(client_key)
        if not state:
            return 0
        _, blocked_until = state
        if blocked_until <= current:
            return 0
        return max(1, int(blocked_until - current + 0.999))


def record_login_failure(client_key: str, now: float | None = None) -> int:
    """Record a failed attempt and return the current retry-after seconds."""
    current = time.time() if now is None else now
    with _LOGIN_LOCK:
        failures, blocked_until = _LOGIN_ATTEMPTS.get(client_key, (0, 0.0))
        failures += 1
        delay_index = min(max(failures - _LOGIN_MAX_FAILURES, 0),
                          len(_LOGIN_BACKOFF_SECONDS) - 1)
        delay = _LOGIN_BACKOFF_SECONDS[delay_index] if failures >= _LOGIN_MAX_FAILURES else 0
        blocked_until = max(blocked_until, current + delay)
        _LOGIN_ATTEMPTS[client_key] = (failures, blocked_until)
        return delay


def clear_login_failures(client_key: str) -> None:
    with _LOGIN_LOCK:
        _LOGIN_ATTEMPTS.pop(client_key, None)


def prune_login_failures(now: float | None = None) -> None:
    """Bound memory for long-lived workers without retaining credentials."""
    current = time.time() if now is None else now
    with _LOGIN_LOCK:
        for key, (_, blocked_until) in list(_LOGIN_ATTEMPTS.items()):
            if blocked_until + _LOGIN_STATE_TTL_SECONDS <= current:
                _LOGIN_ATTEMPTS.pop(key, None)


# Passwords that must never open the plane even if a deployment ships them
# as placeholders (e.g. committed dev defaults): they behave exactly like an
# unset password (open in dev, fail-closed in production).
PLACEHOLDER_PASSWORDS = {"dev-admin-password", "dev-admin", "admin", "password",
                         "change-me", "changeme", "123456"}


def configured_password() -> str:
    pw = (os.environ.get("LEAD_ENGINE_ADMIN_PASSWORD") or "").strip()
    return "" if pw.lower() in PLACEHOLDER_PASSWORDS else pw


def enabled() -> bool:
    return bool(configured_password())


def _secret() -> bytes:
    raw = os.environ.get("LEAD_ENGINE_AUTH_SECRET")
    if raw:
        return raw.encode()
    admin_pw = os.environ.get("LEAD_ENGINE_ADMIN_PASSWORD", "dev-only-secret")
    # Derive a distinct signing key using domain-separated SHA-256
    # so the raw admin password is never exposed in HMAC offline cracking oracles
    return hashlib.sha256(b"lead_engine_session_cookie_v1:" + admin_pw.encode()).digest()


def issue_session() -> str:
    expires = str(int(time.time()) + SESSION_TTL_SECONDS)
    nonce = os.urandom(8).hex()
    message = f"{expires}:{nonce}"
    signature = hmac.new(_secret(), message.encode(), hashlib.sha256).hexdigest()
    return f"{expires}.{nonce}.{signature}"


def valid_session(value: str | None) -> bool:
    if not enabled() or not value or "." not in value:
        return not enabled()
    parts = value.split(".")
    if len(parts) == 3:
        expires, nonce, signature = parts
        if not expires.isdigit() or int(expires) < int(time.time()):
            return False
        message = f"{expires}:{nonce}"
        expected = hmac.new(_secret(), message.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)
    if len(parts) == 2:
        expires, signature = parts
        if not expires.isdigit() or int(expires) < int(time.time()):
            return False
        # Check current key derivation
        expected = hmac.new(_secret(), expires.encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(signature, expected):
            return True
        # Also check raw-password secret for pre-existing legacy cookies
        legacy_raw = (os.environ.get("LEAD_ENGINE_AUTH_SECRET") or
                      os.environ.get("LEAD_ENGINE_ADMIN_PASSWORD", "dev-only-secret")).encode()
        legacy_expected = hmac.new(legacy_raw, expires.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, legacy_expected)
    return False


def password_matches(password: str) -> bool:
    configured = configured_password().encode()
    return bool(configured) and hmac.compare_digest(password.encode(), configured)
