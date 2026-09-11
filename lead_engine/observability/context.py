"""Correlation id plumbing.

A single :mod:`contextvars` slot carries the per-request correlation id from
the FastAPI middleware down to any helper / background task that emits a log
record or an event. Reading the value is always safe — when unset the slot
returns ``None`` and log records just omit the field.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import Request

try:
    # FastAPI exposes starlette's BaseHTTPMiddleware; we import lazily so the
    # module is still importable in environments where only the logger /
    # context helpers are needed (e.g. background workers without FastAPI).
    from starlette.middleware.base import BaseHTTPMiddleware
except Exception:  # pragma: no cover - starlette is a fastapi dep in practice.
    BaseHTTPMiddleware = None  # type: ignore[assignment]


#: ContextVar holding the current request's correlation id, or ``None``.
correlation_id_var = __import__("contextvars").ContextVar(
    "correlation_id", default=None
)


def set_correlation_id(cid: str) -> object:
    """Bind *cid* as the current correlation id and return a reset token.

    The returned token is compatible with :meth:`ContextVar.reset` so callers
    can restore the previous value when they finish a logical unit of work.
    """
    return correlation_id_var.set(cid)


def get_correlation_id() -> Optional[str]:
    """Return the current correlation id, or ``None`` if none is set."""
    return correlation_id_var.get()


def correlation_id_from_request(request: Request) -> str:
    """Read the ``X-Correlation-ID`` header off *request* or mint a new one."""
    cid = request.headers.get("X-Correlation-ID")
    if cid:
        return cid
    return uuid.uuid4().hex


class CorrelationIdMiddleware:
    """ASGI-style FastAPI middleware that propagates correlation ids.

    Uses the classic ``__init__`` / ``__call__`` shape so it does not depend
    on :class:`starlette.middleware.base.BaseHTTPMiddleware` (which adds a
    threadpool hop and historically has edge cases around exception
    propagation). For each request we:

    1. Read ``X-Correlation-ID`` off the incoming request, or generate
       ``uuid4().hex`` if it is missing.
    2. Stash the value in :data:`correlation_id_var` so every log record
       emitted while handling the request can pull it out via
       :func:`get_correlation_id`.
    3. Restore the previous value when the request finishes (so a worker
       that serves multiple concurrent requests does not leak ids across
       them).
    4. Echo the id back to the client as ``X-Correlation-ID`` on the
       response.

    The middleware is intentionally tiny: it does not touch the body, does
    not wrap exceptions, and never short-circuits the response.
    """

    HEADER_NAME = "X-Correlation-ID"

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            # Lifespan / websocket — nothing to do.
            await self.app(scope, receive, send)
            return

        # Pull the header (case-insensitively — Starlette already lower-cases).
        cid: Optional[str] = None
        for raw_name, raw_value in scope.get("headers", []):
            if raw_name == b"x-correlation-id":
                try:
                    cid = raw_value.decode("latin-1").strip()
                except Exception:
                    cid = None
                break

        if not cid:
            cid = uuid.uuid4().hex

        token = correlation_id_var.set(cid)

        async def send_wrapper(message):
            if message.get("type") == "http.response.start":
                # Inject / overwrite the response header.
                headers = list(message.get("headers", []))
                # Strip any existing header so we don't emit duplicates.
                headers = [
                    (k, v) for (k, v) in headers
                    if k != b"x-correlation-id"
                ]
                headers.append((b"x-correlation-id", cid.encode("latin-1")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            correlation_id_var.reset(token)


# Expose BaseHTTPMiddleware at module level so callers that prefer the
# ``add_middleware(BaseHTTPMiddleware, dispatch=...)`` form can still find
# it without reaching into ``starlette`` directly.
__all__ = [
    "correlation_id_var",
    "set_correlation_id",
    "get_correlation_id",
    "correlation_id_from_request",
    "CorrelationIdMiddleware",
    "BaseHTTPMiddleware",
]
