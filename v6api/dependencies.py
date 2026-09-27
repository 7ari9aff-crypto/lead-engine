"""V6 API dependencies: authentication, tenant resolution, service container.

AuthN: service token (CLI/tests/n8n) OR Supabase JWT (dashboard users).
AuthZ: role checked per route; tenant always resolved from the verified
principal — never from client-controlled headers except for the service
principal (X-Org-Id), which is the documented operator bridge.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import jwt as pyjwt
from fastapi import HTTPException, Request

from application.ports import Principal
from infrastructure.config import Settings


@dataclass
class Container:
    settings: Settings
    db: Any
    vault: Any
    gateway: Any
    model_gateway: Any
    handlers: dict
    relay: Any = None
    doctor: Any = None


_container: Container | None = None


def init_container(container: Container) -> None:
    global _container
    _container = container


def get_container() -> Container:
    assert _container is not None, "container not initialized"
    return _container


def resolve_principal(request: Request) -> Principal:
    container = get_container()
    settings = container.settings
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip()

    if not token:
        raise HTTPException(status_code=401, detail="authentication required")

    if token == settings.service_token:
        org_id = request.headers.get("X-Org-Id", "") or None
        return Principal(org_id=org_id, user_ext_id="service", role="service", is_service=True)

    if settings.supabase_jwt_secret:
        try:
            claims = pyjwt.decode(
                token, settings.supabase_jwt_secret,
                algorithms=["HS256"], audience="authenticated",
            )
        except pyjwt.PyJWTError as exc:
            raise HTTPException(status_code=401, detail=f"invalid token: {exc}") from exc
        sub = str(claims.get("sub", ""))
        with container.db.tx_system() as conn, conn.cursor() as cur:
            member = cur.execute(
                """SELECT m.org_id, m.role FROM platform.members m
                   WHERE m.user_ext_id = %s LIMIT 1""",
                (sub,),
            ).fetchone()
        if member is None:
            raise HTTPException(status_code=403, detail="no organization membership")
        return Principal(org_id=str(member["org_id"]), user_ext_id=sub,
                         role=str(member["role"]))

    raise HTTPException(status_code=401, detail="authentication required")


def require_service(request: Request) -> Principal:
    """Operator/CLI surface (org bootstrap, maintenance) — no org required."""
    principal = resolve_principal(request)
    if not principal.is_service:
        raise HTTPException(status_code=403, detail="service token required")
    return principal


def require_principal(request: Request) -> Principal:
    principal = resolve_principal(request)
    if not principal.org_id:
        raise HTTPException(status_code=401, detail="service principal requires X-Org-Id")
    return principal


def require_manager(request: Request) -> Principal:
    principal = resolve_principal(request)
    if not principal.can_manage():
        raise HTTPException(status_code=403, detail="owner or admin role required")
    return principal


def map_domain_errors(exc: Exception) -> HTTPException:
    from contracts.errors import (
        AuthorizationError,
        DomainError,
        EntitlementExceeded,
        LeaseLostError,
        NotFoundError,
        PolicyBlocked,
    )

    if isinstance(exc, NotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, EntitlementExceeded):
        return HTTPException(status_code=402, detail=str(exc))
    if isinstance(exc, PolicyBlocked):
        return HTTPException(status_code=451, detail=str(exc))
    if isinstance(exc, (AuthorizationError, LeaseLostError)):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, DomainError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail="internal error")
