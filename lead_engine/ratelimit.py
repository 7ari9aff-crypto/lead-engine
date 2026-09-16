"""General API rate limiting (gap #1).

Login had its own throttle; everything else was unthrottled. This is a
small in-process token-bucket middleware: per (client IP, path-prefix)
bucket, configurable via env. Multi-worker deployments get per-process
buckets — acceptable for abuse mitigation (not exact accounting).

Env knobs:
  LEAD_ENGINE_RATE_LIMIT=1          enable (default: enabled)
  LEAD_ENGINE_RATE_LIMIT_RPS=8      sustained requests/sec per bucket
  LEAD_ENGINE_RATE_LIMIT_BURST=40   burst capacity per bucket
Exempt: /health, /ready, /api/v1/ready, /api/auth/session (liveness +
dashboard session probe), static assets, and machine clients bearing
LEAD_ENGINE_MCP_TOKEN (their load is orchestrated, not abusive).
"""
import os
import threading
import time

_EXEMPT_EXACT = frozenset({
    "/health", "/ready", "/api/v1/ready", "/api/auth/session",
    "/api/auth/logout",
})
_EXEMPT_PREFIXES = ("/static",)


def _parse_float(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, ""))
        return value if value > 0 else default
    except (TypeError, ValueError):
        return default


class RateLimiter:
    def __init__(self, rps: float = 8.0, burst: float = 40.0):
        self.rps = rps
        self.burst = burst
        self._buckets: dict = {}
        self._lock = threading.Lock()

    def _key(self, scope) -> tuple:
        client = scope.get("client")
        ip = client[0] if client else "unknown"
        path = scope.get("path", "")
        # Group by first two path segments so one hot endpoint can't eat
        # the budget of unrelated routes, while per-job polling shares one.
        parts = [p for p in path.split("/") if p][:2]
        return (ip, "/" + "/".join(parts))

    def _is_exempt(self, scope) -> bool:
        if scope.get("type") != "http":
            return True
        path = scope.get("path", "")
        if path in _EXEMPT_EXACT or path.startswith(_EXEMPT_PREFIXES):
            return True
        if scope.get("method") == "OPTIONS":  # CORS preflight
            return True
        if path == "/api/auth/login":  # own stricter throttle
            return True
        return False

    def _machine_client(self, scope) -> bool:
        expected = os.environ.get("LEAD_ENGINE_MCP_TOKEN", "")
        if not expected:
            return False
        import hmac as _hmac

        for name, value in scope.get("headers", []):
            if name == b"authorization":
                try:
                    scheme, _, token = value.decode("latin-1").partition(" ")
                    if scheme.lower() == "bearer" and token:
                        return _hmac.compare_digest(token, expected)
                except Exception:
                    return False
        return False

    def allow(self, scope) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds)."""
        if self._is_exempt(scope) or self._machine_client(scope):
            return True, 0
        now = time.monotonic()
        key = self._key(scope)
        with self._lock:
            tokens, updated = self._buckets.get(key, (self.burst, now))
            tokens = min(self.burst, tokens + (now - updated) * self.rps)
            if tokens >= 1.0:
                self._buckets[key] = (tokens - 1.0, now)
                return True, 0
            self._buckets[key] = (tokens, now)
            deficit = 1.0 - tokens
            retry_after = max(1, int(deficit / self.rps) + 1)
            return False, retry_after

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


_limiter = RateLimiter(
    rps=_parse_float("LEAD_ENGINE_RATE_LIMIT_RPS", 8.0),
    burst=_parse_float("LEAD_ENGINE_RATE_LIMIT_BURST", 40.0),
)


def _enabled() -> bool:
    return os.environ.get("LEAD_ENGINE_RATE_LIMIT", "1").strip() not in (
        "", "0", "false", "no", "off")


class RateLimitMiddleware:
    """ASGI middleware — 429 + Retry-After when a bucket is exhausted."""

    def __init__(self, app, limiter: RateLimiter | None = None):
        self.app = app
        self.limiter = limiter or _limiter

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and _enabled():
            allowed, retry_after = self.limiter.allow(scope)
            if not allowed:
                from starlette.responses import JSONResponse

                resp = JSONResponse(
                    {"detail": "too many requests"}, status_code=429)
                resp.headers["Retry-After"] = str(retry_after)
                await resp(scope, receive, send)
                return
        await self.app(scope, receive, send)
