"""Bridge: mount the V6 router into the legacy FastAPI app (single origin).

Auth bridging (fail-closed):
1. Legacy Supabase JWT claims (set by the legacy admin_session_guard) →
   V6 membership lookup by user_ext_id → org + role.
2. Legacy cookie session (open / password modes) → LEAD_ENGINE_ORG_ID bridge
   (the operator's deployment org) as owner — the documented dev posture.
3. V6 service token + X-Org-Id — operator/CLI path (unchanged).
Everything else 401s.
"""
from __future__ import annotations

import os

from fastapi import HTTPException, Request

from v6api.app import build_v6_router
from application.ports import Principal


def _bridge_principal(request: Request) -> Principal:
    from v6api.dependencies import get_container

    container = get_container()
    settings = container.settings

    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip()
    if token and token == settings.service_token:
        org_id = request.headers.get("X-Org-Id", "") or None
        if not org_id:
            raise HTTPException(status_code=401, detail="service principal requires X-Org-Id")
        return Principal(org_id=org_id, user_ext_id="service", role="service", is_service=True)

    claims = getattr(request.state, "claims", None)
    sub = str((claims or {}).get("sub", "")).strip()
    if sub:
        with container.db.tx_system() as conn, conn.cursor() as cur:
            member = cur.execute(
                """SELECT m.org_id, m.role FROM platform.members m
                   WHERE m.user_ext_id = %s LIMIT 1""",
                (sub,),
            ).fetchone()
        if member is not None:
            role = str(member["role"])
            return Principal(org_id=str(member["org_id"]), user_ext_id=sub, role=role)
        org_bridge = (os.environ.get("LEAD_ENGINE_ORG_ID") or "").strip()
        if org_bridge:
            return Principal(org_id=org_bridge, user_ext_id=sub, role="owner")

    # legacy cookie session (open / password modes)
    from lead_engine.api import auth as legacy_auth

    if legacy_auth.valid_session(request.cookies.get(legacy_auth.COOKIE_NAME)):
        org_bridge = (os.environ.get("LEAD_ENGINE_ORG_ID") or "").strip()
        if org_bridge:
            return Principal(org_id=org_bridge, user_ext_id="legacy-cookie",
                             role="owner")
        if not legacy_auth.enabled():
            raise HTTPException(
                status_code=401,
                detail="open mode needs LEAD_ENGINE_ORG_ID for tenant resolution")
    raise HTTPException(status_code=401, detail="authentication required")


def _bridge_manager(request: Request) -> Principal:
    principal = _bridge_principal(request)
    if not principal.can_manage():
        raise HTTPException(status_code=403, detail="owner or admin role required")
    return principal


def mount_v6(legacy_app) -> None:
    """Attach the V6 engine to the legacy application (idempotent guard)."""
    if getattr(legacy_app.state, "v6_mounted", False):
        return
    legacy_app.state.v6_mounted = True

    from v6api.app import Container  # noqa: F401 — typing surface
    from application.handlers.pipeline import AcquisitionPipelineHandler
    from infrastructure.config import Settings
    from infrastructure.events.relay import OutboxRelay
    from infrastructure.pii.vault import PiiVault
    from infrastructure.postgres.pool import Database
    from infrastructure.config import MIGRATIONS_DIR
    from infrastructure.doctor.registry import build_doctor
    from infrastructure.providers.bootstrap import build_gateway, build_model_gateway
    from infrastructure.repos.doctor_repo import DoctorRepo

    settings = Settings.load()
    try:
        from lead_engine.db import open_db as _legacy_open_db
        from lead_engine.secrets import hydrate_environment as _hydrate

        _hydrate(_legacy_open_db(), os.environ.get("LEAD_ENGINE_ORG_ID"))
    except Exception:
        pass
    db = Database(settings.database_url)
    vault = PiiVault(db, settings)
    gateway = build_gateway()
    model_gateway = build_model_gateway()
    doctor = build_doctor(DoctorRepo(db, MIGRATIONS_DIR), vault=vault,
                          gateway=gateway, model_gateway=model_gateway)
    container = Container(
        settings=settings, db=db, vault=vault,
        gateway=gateway, model_gateway=model_gateway,
        doctor=doctor,
        handlers={"acquisition.run": AcquisitionPipelineHandler()},
        relay=OutboxRelay(db, consumer=lambda event: None,
                          batch_size=settings.relay_batch_size),
    )
    init_done = getattr(legacy_app.state, "v6_container", None)
    if init_done is None:
        from v6api.dependencies import init_container

        init_container(container)
        legacy_app.state.v6_container = container

    # Embedded mode namespaces V6 under /v6 — the legacy app already owns
    # /api/v1/* and registration order would shadow the V6 projection reads.
    # The included router is moved to the FRONT of the match order: newer
    # Starlette's _IncludedRouter defers to same-path legacy routes otherwise.
    legacy_app.include_router(build_v6_router(container), prefix="/v6")
    try:
        included = legacy_app.router.routes.pop()
        legacy_app.router.routes.insert(0, included)
    except IndexError:  # pragma: no cover — router always non-empty
        pass

    legacy_app.dependency_overrides[require_principal_ref()] = _bridge_principal
    legacy_app.dependency_overrides[require_manager_ref()] = _bridge_manager

    import atexit

    atexit.register(db.close)


def require_principal_ref():
    from v6api.dependencies import require_principal

    return require_principal


def require_manager_ref():
    from v6api.dependencies import require_manager

    return require_manager
