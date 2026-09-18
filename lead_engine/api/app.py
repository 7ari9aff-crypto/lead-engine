"""FastAPI layer — the engine as an HTTP service.

This is the piece n8n talks to:
  POST /benchmark/run      run the live pipeline
  GET  /jobs/{job_id}      job state + stage summary (COMPLETED / PAUSED / ...)
  POST /jobs/{id}/resume   resume a PAUSED job
  GET  /leads              exported leads (filter by job/stage)
  POST /sync-supabase      push leads into the Supabase lead database
  POST /verify-email       5-state email verification
  GET  /providers          registry status + usage

The control dashboard (Arabic RTL) is served from /static and mounted at /.
Admin endpoints live under /api/*: system status, provider toggle/reset,
YAML config editing, background job start, cache purge, CSV export.
"""
import hmac
import json
import ipaddress
import os
import sys
import threading
from typing import Any, Literal
from urllib.parse import urlparse

import yaml
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

try:
    from pydantic import EmailStr
    import email_validator  # noqa: F401 — EmailStr's optional runtime dependency.
except (ImportError, ModuleNotFoundError):
    EmailStr = str  # type: ignore[misc,assignment]


MAX_SEED_PATH = 4_096
MAX_MAPPING_ITEMS = 32

from .. import __version__
from ..benchmark.metrics import compute_metrics, render_report
from ..config import (
    CONFIG_DIR, DB_PATH, DATA_DIR, OUTPUTS_DIR, ROOT, load_env, load_settings,
)
from ..db import open_db, Database
from ..agent_registry import AgentRegistry
from .policy_api import router as policy_router
from ..jobs import PAUSED, JobManager
from ..providers.email import VerificationPipeline
from ..registry import Registry
from ..router import Router

load_env()
DATA_DIR.mkdir(exist_ok=True)
settings = load_settings()

# Org-scoped provider credentials live encrypted in the platform DB; hydrate
# them into the process env so every provider adapter reads them unchanged.
def _hydrate_credentials_at_boot() -> None:
    try:
        from ..secrets import hydrate_environment

        db = open_db()
        hydrate_environment(db, os.environ.get("LEAD_ENGINE_ORG_ID"))
        db.close()
    except Exception:
        pass  # no DSN/org/key yet — .env bootstrap path



def _recover_interrupted_jobs_at_boot() -> None:
    try:
        from ..jobs import JobManager
        from ..queue import platform_mode, reclaim_expired

        db = open_db()
        if platform_mode():
            reclaim_expired(db)
        else:
            JobManager(db).recover_interrupted_jobs()
        db.close()
    except Exception:
        pass


_hydrate_credentials_at_boot()
_recover_interrupted_jobs_at_boot()

STATIC_DIR = ROOT / "lead_engine" / "static"
CONFIG_FILES = {
    "settings": CONFIG_DIR / "settings.yaml",
    "cache_policy": CONFIG_DIR / "cache_policy.yaml",
    "icp": CONFIG_DIR / "icp" / "v0.yaml",
    "legal": CONFIG_DIR / "legal_policies" / "default.yaml",
    "legal_sa": CONFIG_DIR / "legal_policies" / "sa.yaml",
}

app = FastAPI(
    title="Lead Engine API",
    version=__version__,
    description="Quota-aware multi-provider lead generation engine "
                "(n8n = orchestration, FastAPI = brain, Supabase = storage)",
)


def _cors_origins() -> list[str]:
    """Return explicit CORS origins, with localhost defaults for development.

    Production must opt in to browser origins via LEAD_ENGINE_CORS_ORIGINS.
    Wildcards are intentionally ignored because credentials are enabled for
    the dashboard's cookie/session flow.
    """
    configured = os.environ.get("LEAD_ENGINE_CORS_ORIGINS")
    if configured is None:
        if os.environ.get("LEAD_ENGINE_ENV") == "production":
            return []
        configured = "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173"

    origins = []
    for value in configured.split(","):
        origin = value.strip().rstrip("/")
        parsed = urlparse(origin)
        if (not origin or origin == "*" or parsed.scheme not in {"http", "https"}
                or not parsed.netloc or parsed.path not in ("", "/")
                or parsed.params or parsed.query or parsed.fragment):
            continue
        if origin not in origins:
            origins.append(origin)
    return origins


_CORS_ORIGINS = _cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=bool(_CORS_ORIGINS),
    allow_methods=["*"],
    allow_headers=["*"],
)

from ..observability import CorrelationIdMiddleware
app.add_middleware(CorrelationIdMiddleware)
from ..ratelimit import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware)
from fastapi.middleware.gzip import GZipMiddleware
# API JSON payloads (providers, leads lists, status) are several KB of highly
# repetitive JSON: gzip cuts the dashboard's transfer by ~80% on the same
# server. Streaming responses (SSE) are excluded by default (see
# starlette.middleware.gzip DEFAULT_EXCLUDED_CONTENT_TYPES).
app.add_middleware(GZipMiddleware, minimum_size=1024)


# ===== SLO instrumentation (Observability, plan-improvement T3) =====
# Records every served request into the in-process registry that backs
# GET /metrics and GET /api/v1/slo. Labelled by *route template* (not the raw
# path) so /api/v1/leads/abc and /api/v1/leads/xyz share one series and the
# label cardinality stays bounded by the number of routes.
from .metrics_api import REGISTRY as _METRICS  # noqa: E402


class _MetricsMiddleware:
    """Pure ASGI middleware — cheaper than a BaseHTTPMiddleware wrapper."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        status_holder = {"status": 500}

        async def _send(message):
            if message["type"] == "http.response.start":
                status_holder["status"] = message.get("status", 500)
            await send(message)

        try:
            await self.app(scope, receive, _send)
        finally:
            route = scope.get("route")
            path = getattr(route, "path", None) or scope.get("path", "unknown")
            # Static assets and the SPA fallback would otherwise dominate the
            # series list with one entry per asset hashed filename.
            if not path.startswith("/assets/"):
                _METRICS.observe(
                    scope.get("method", "GET"),
                    path,
                    status_holder["status"],
                    time.perf_counter() - started,
                )


import time  # noqa: E402

app.add_middleware(_MetricsMiddleware)

PROTECTED_PATHS = ("/api/", "/mcp", "/leads", "/jobs", "/providers", "/benchmark/",
                   "/sync-supabase", "/verify-email", "/report/", "/export/",
                   "/docs", "/redoc", "/openapi.json", "/metrics")


@app.middleware("http")
async def admin_session_guard(request: Request, call_next):
    from . import auth_jwt
    from .auth import COOKIE_NAME, valid_session

    path = request.url.path
    # Single-origin dashboard: browser navigations to paths that double as
    # API routes (/jobs, /leads, /providers) must get the SPA, while API
    # clients (curl, n8n) keep receiving JSON. The HTML response MUST be
    # no-cache: otherwise the browser caches it under the API path and the
    # app's own fetch to that path receives HTML instead of JSON.
    if request.method == "GET" and path in {"/jobs", "/leads", "/providers"} \
            and "text/html" in request.headers.get("accept", ""):
        index = STATIC_DIR / "index.html"
        if index.exists():
            resp = FileResponse(index)
            resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            resp.headers["Pragma"] = "no-cache"
            resp.headers["Expires"] = "0"
            return resp
    public = path in {
        "/health", "/ready", "/api/v1/ready",
        "/api/auth/login", "/api/auth/session", "/api/auth/logout",
        # Stripe signs webhook deliveries with its own HMAC (verified inside
        # the handler) — JWT auth cannot apply to an outbound caller.
        "/api/v1/billing/webhook",
    }
    protected = path.startswith(PROTECTED_PATHS)
    if protected and not public:
        token = auth_jwt.bearer_token(request.headers)
        claims = auth_jwt.validate_supabase_jwt(token) if token else None
        # Legacy cookie sessions are valid ONLY in non-Supabase modes. With
        # Supabase configured, an anonymous request must never fall through
        # just because no admin password is set (valid_session would say ok).
        mode = auth_jwt.auth_mode()
        if mode == "closed":
            return JSONResponse({"detail": "authentication required"}, status_code=401)
        # Machine clients (n8n scheduler, workers, MCP) authenticate with the
        # dedicated static token LEAD_ENGINE_MCP_TOKEN on ANY protected path —
        # opt-in via env, fail-closed when unset. This keeps the n8n scheduler
        # working (it has no Supabase session and no cookie).
        _expected = os.environ.get("LEAD_ENGINE_MCP_TOKEN", "")
        machine_ok = bool(_expected) and isinstance(token, str) and \
            hmac.compare_digest(token.encode(), _expected.encode())
        legacy_ok = (
            mode in ("open", "password")
            and valid_session(request.cookies.get(COOKIE_NAME))
        )
        if claims is None and not machine_ok and not legacy_ok:
            return JSONResponse({"detail": "authentication required"}, status_code=401)
        # Request-scoped tenant context: downstream handlers resolve the org
        # from the verified token subject instead of the env bridge.
        request.state.claims = claims
    return await call_next(request)


def require_admin(request: Request = None, db: Database = None):
    """RBAC guard for mutating management endpoints. Token-less contexts
    (worker/n8n) pass through on the env bridge; token'd callers must be
    owner/admin of their active organization."""
    if request is None or db is None:
        return
    claims = getattr(request.state, "claims", None)
    if not claims:
        return
    from . import auth_jwt

    if not auth_jwt.is_admin(claims, db):
        raise HTTPException(status_code=403,
                            detail="العملية دي محتاجة صلاحية مالك أو مشرف")


def _org_clause(db, column: str = "organization_id") -> tuple[str, list]:
    """Delegated to lead_engine.tenant so chat tools, MCP and these
    endpoints share ONE tenant predicate with identical semantics."""
    from ..tenant import org_clause

    return org_clause(db, column)


def get_db(request: Request = None):
    """Per-request DB handle. The tenant org comes from the verified JWT
    (membership lookup) and falls back to the LEAD_ENGINE_ORG_ID bridge for
    worker/n8n/service contexts. One connection per request: the membership
    lookup reuses the same handle (org_id is a plain attribute)."""
    db = open_db()
    try:
        if request is not None:
            claims = getattr(request.state, "claims", None)
            if claims:
                from . import auth_jwt

                resolved = auth_jwt.resolve_org_id(claims, db)
                if resolved:
                    db.org_id = resolved
                else:
                    # Authenticated but belongs to no organization: never let
                    # the env bridge act as their tenant.
                    db.org_id = "__no_org__"
            elif not getattr(db, "org_id", None):
                # Preserve the worker/service bridge for token-less contexts;
                # browser requests always take the verified claims branch above.
                db.org_id = os.environ.get("LEAD_ENGINE_ORG_ID")
        yield db
    finally:
        db.conn.close()


def _validate_bounded_mapping(value, *, name: str):
    if not isinstance(value, dict) or len(value) > MAX_MAPPING_ITEMS:
        raise ValueError(f"{name} must contain at most {MAX_MAPPING_ITEMS} items")
    for key, nested in value.items():
        if not isinstance(key, str) or len(key) > 128:
            raise ValueError(f"{name} keys are too long")
        if isinstance(nested, str) and len(nested) > 16_384:
            raise ValueError(f"{name} text values are too long")
        if isinstance(nested, (list, tuple)) and len(nested) > MAX_MAPPING_ITEMS:
            raise ValueError(f"{name} lists are too large")
        if isinstance(nested, dict):
            _validate_bounded_mapping(nested, name=name)
    return value


class RunRequest(BaseModel):
    icp: str = Field(default="v0", min_length=1, max_length=128)
    seed_csv: str | None = Field(default=None, min_length=1, max_length=MAX_SEED_PATH)
    overrides: dict[str, Any] | None = Field(default=None, max_length=MAX_MAPPING_ITEMS)

    @field_validator("overrides")
    @classmethod
    def validate_overrides(cls, value):
        return None if value is None else _validate_bounded_mapping(value, name="overrides")


class ResumeRequest(BaseModel):
    pass


class VerifyRequest(BaseModel):
    email: EmailStr = Field(..., max_length=320)

    @field_validator("email")
    @classmethod
    def validate_email_fallback(cls, value):
        # EmailStr performs full validation when email-validator is installed;
        # retain a conservative fallback when the optional extra is absent.
        text = str(value).strip()
        if "@" not in text or text.startswith("@") or text.endswith("@"):
            raise ValueError("invalid email address")
        return value


class SyncRequest(BaseModel):
    job_id: str
    stage: str = "ACCEPTED"


class AgentRunRequest(BaseModel):
    agent: str = Field(default="lead-generation", min_length=1, max_length=128)
    input: dict[str, Any] = Field(default_factory=dict, max_length=MAX_MAPPING_ITEMS)
    version: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("input")
    @classmethod
    def validate_input(cls, value):
        return _validate_bounded_mapping(value, name="input")


class AgentCreateRequest(BaseModel):
    slug: str = Field(..., min_length=2, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str = Field(..., min_length=1, max_length=120)
    description: str = ""
    status: str = "draft"


class AgentUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None


class AgentVersionCreateRequest(BaseModel):
    version: str = Field(..., min_length=1, max_length=32)
    instructions: str | None = None
    model_provider: str | None = "router"
    model_name: str | None = None
    thinking_effort: str | None = None
    tool_policy: dict | None = None
    output_schema: dict | None = None
    status: str = "draft"
    activate: bool = True


class ToolRegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    description: str = ""
    input_schema: dict | None = None
    output_schema: dict | None = None
    scopes: list[str] | None = None
    requires_approval: bool = False
    enabled: bool = True


class ConnectionRegisterRequest(BaseModel):
    connection_id: str = Field(..., min_length=2, max_length=80)
    provider: str = Field(..., min_length=1, max_length=80)
    kind: str = "custom"
    base_url: str | None = None
    status: str = "configured"
    metadata: dict | None = None


class ApprovalResolution(BaseModel):
    status: str


class LoginRequest(BaseModel):
    password: str = Field(..., min_length=1, max_length=1_024)


@app.post("/api/auth/login")
def auth_login(req: LoginRequest, request: Request):
    from .auth import (COOKIE_NAME, clear_login_failures, issue_session,
                       login_retry_after, password_matches, prune_login_failures,
                       record_login_failure)

    client_key = request.client.host if request.client else "unknown"
    prune_login_failures()
    retry_after = login_retry_after(client_key)
    if retry_after:
        response = JSONResponse({"detail": "too many login attempts"}, status_code=429)
        response.headers["Retry-After"] = str(retry_after)
        return response

    # P0.3 auth finalization: when Supabase Auth is the backend, the legacy
    # shared-password path is closed — users sign in with email via the
    # frontend Supabase client. Legacy stays only for local/no-Supabase dev.
    from . import auth_jwt
    if auth_jwt.auth_mode() == "supabase":
        raise HTTPException(
            status_code=403,
            detail="تسجيل الدخول بيتم بالبريد الإلكتروني — استخدم صفحة الدخول العادية",
        )
    if not password_matches(req.password):
        retry_after = record_login_failure(client_key)
        if retry_after:
            response = JSONResponse({"detail": "too many login attempts"}, status_code=429)
            response.headers["Retry-After"] = str(retry_after)
            return response
        raise HTTPException(status_code=401, detail="invalid credentials")
    clear_login_failures(client_key)
    response = JSONResponse({"authenticated": True})
    response.set_cookie(COOKIE_NAME, issue_session(), httponly=True, samesite="lax",
                        secure=bool(os.environ.get("LEAD_ENGINE_COOKIE_SECURE")),
                        max_age=60 * 60 * 12)
    return response


@app.get("/api/auth/session")
def auth_session(request: Request, db: Database = Depends(get_db)):
    from . import auth_jwt
    from .auth import COOKIE_NAME, enabled, valid_session

    token = auth_jwt.bearer_token(request.headers)
    claims = auth_jwt.validate_supabase_jwt(token) if token else None
    cookie_ok = valid_session(request.cookies.get(COOKIE_NAME))
    mode = auth_jwt.auth_mode()
    if mode == "supabase":
        authenticated = claims is not None
    elif mode == "closed":
        # "closed" means the middleware rejects every protected request with
        # 401. Reporting authenticated=True here was contradictory and caused
        # the frontend to render the dashboard then crash on every API call.
        authenticated = False
    else:
        authenticated = (not enabled()) or cookie_ok
    org_id = None
    if authenticated:
        if claims:
            from ..tenant import apply_context

            try:
                apply_context(db, request)
                org_id = getattr(db, "org_id", None)
                if org_id and str(org_id).startswith("__"):
                    org_id = None
            except Exception:
                org_id = None
        elif cookie_ok:
            # Legacy cookie session: machine/local context only — the env
            # bridge org, never NULL ambiguity.
            org_id = os.environ.get("LEAD_ENGINE_ORG_ID")
    return {"authenticated": authenticated, "mode": mode,
            "org_id": org_id}


@app.post("/api/auth/logout")
def auth_logout():
    from .auth import COOKIE_NAME

    response = JSONResponse({"authenticated": False})
    response.delete_cookie(COOKIE_NAME)
    return response


@app.get("/api/v1/health")
def health_detail(db: Database = Depends(get_db)):
    """Protected health detail: which providers are configured."""
    router = Router(db, _cache(db), settings)
    providers = router.status_report()
    live = sorted({r["name"] for r in providers if r.get("has_key")})
    return {
        "status": "ok",
        "providers_configured": live,
        "note": "live provider pool depends on .env keys; missing keys are unavailable",
    }


@app.get("/health")
def health_public():
    """Unauthenticated liveness probe - no provider or tenant details."""
    return {"status": "ok"}


@app.get("/api/v1/ready")
@app.get("/ready")
def readiness(db: Database = Depends(get_db)):
    """Lightweight readiness probe: confirm the configured DB is reachable."""
    try:
        db.execute("SELECT 1")
    except Exception as exc:
        raise HTTPException(status_code=503, detail="database not ready") from exc
    return {"status": "ready"}


@app.get("/api/agents")
def api_agents(db: Database = Depends(get_db)):
    return {"agents": AgentRegistry(db).agents()}


@app.get("/api/agents/{slug}/versions")
def api_agent_versions(slug: str, db: Database = Depends(get_db)):
    return {"versions": AgentRegistry(db).versions(slug)}


@app.post("/api/agent-runs")
def api_agent_run_create(req: AgentRunRequest, request: Request, db: Database = Depends(get_db)):
    require_admin(request, db)
    try:
        run_id = AgentRegistry(db).create_run(req.agent, req.input, req.version)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="operation could not be completed") from exc
    return {"run_id": run_id, "status": "RUNNING", "agent": req.agent}


@app.get("/api/agent-runs")
def api_agent_runs(limit: int = Query(default=50, ge=1, le=200), db: Database = Depends(get_db)):
    return {"runs": AgentRegistry(db).runs(limit)}


@app.get("/api/agent-runs/{run_id}")
def api_agent_run(run_id: str, db: Database = Depends(get_db)):
    row = AgentRegistry(db).run(run_id)
    if not row:
        raise HTTPException(status_code=404, detail="agent run not found")
    return row


@app.get("/api/tools")
def api_tools(db: Database = Depends(get_db)):
    return {"tools": AgentRegistry(db).tools()}


@app.get("/api/connections")
def api_connections(db: Database = Depends(get_db)):
    return {"connections": AgentRegistry(db).connections()}


@app.post("/api/connections/{provider}/check")
def api_connection_check(provider: str, request: Request, db: Database = Depends(get_db)):
    require_admin(request, db)
    result = AgentRegistry(db).check_connection(provider)
    if not result:
        raise HTTPException(status_code=404, detail="provider connection not found")
    return result


@app.get("/api/approvals")
def api_approvals(status: str = "PENDING", db: Database = Depends(get_db)):
    return {"approvals": AgentRegistry(db).approvals(status)}


@app.post("/api/approvals/{approval_id}/resolve")
def api_approval_resolve(approval_id: str, req: ApprovalResolution,
                         request: Request, db: Database = Depends(get_db)):
    require_admin(request, db)
    if req.status not in ("APPROVED", "REJECTED"):
        raise HTTPException(status_code=422, detail="status must be APPROVED or REJECTED")
    if not AgentRegistry(db).resolve_approval(approval_id, req.status):
        raise HTTPException(status_code=404, detail="pending approval not found")
    return {"ok": True, "approval_id": approval_id, "status": req.status}


# ===== Code-aware agent operations (diagnose freely, patch on approval) =====

@app.get("/api/approvals/{approval_id}")
def api_approval_detail(approval_id: str, request: Request,
                        db: Database = Depends(get_db)):
    """Full approval row incl. the parsed payload (the patch diff for review)."""
    require_admin(request, db)
    row = AgentRegistry(db).approval(approval_id)
    if not row:
        raise HTTPException(status_code=404, detail="approval not found")
    payload = None
    if row.get("payload_json"):
        try:
            payload = json.loads(row["payload_json"])
        except (json.JSONDecodeError, TypeError):
            payload = None
    return {"approval": {**row, "payload": payload}}


@app.post("/api/approvals/{approval_id}/apply")
def api_approval_apply(approval_id: str, request: Request,
                       db: Database = Depends(get_db)):
    """Apply an APPROVED code patch onto a fresh git branch (never main)."""
    require_admin(request, db)
    from .. import codeops
    try:
        return codeops.apply_patch(db, approval_id, actor="operator")
    except codeops.ApprovalRequired as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except codeops.CodeOpsError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/api/approvals/{approval_id}/revert")
def api_approval_revert(approval_id: str, request: Request,
                        db: Database = Depends(get_db)):
    """Undo an applied patch: restore backups and return to the base branch."""
    require_admin(request, db)
    from .. import codeops
    try:
        return codeops.revert_patch(db, approval_id, actor="operator")
    except codeops.CodeOpsError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.get("/api/code/workspace")
def api_code_workspace(prefix: str = "", depth: int = 2, limit: int = 300,
                       request: Request = None, db: Database = Depends(get_db)):
    """Read-only file tree of the workspace (secrets and vendor dirs excluded)."""
    require_admin(request, db)
    from .. import codeops
    try:
        return codeops.list_code(prefix, depth, limit)
    except codeops.CodeOpsError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.get("/api/code/file")
def api_code_file(path: str, start_line: int | None = None,
                  end_line: int | None = None, request: Request = None,
                  db: Database = Depends(get_db)):
    """Read one workspace source file (optionally a line window)."""
    require_admin(request, db)
    from .. import codeops
    try:
        return codeops.read_code(path, start_line, end_line)
    except codeops.CodeOpsError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.get("/api/code/search")
def api_code_search(pattern: str, glob: str | None = None, limit: int = 50,
                    request: Request = None, db: Database = Depends(get_db)):
    """Regex search across the workspace source tree."""
    require_admin(request, db)
    from .. import codeops
    try:
        return codeops.search_code(pattern, glob, limit)
    except codeops.CodeOpsError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# ===== Dynamic agent registry (UI-driven, multi-domain) =====

@app.post("/api/agents")
def api_agents_create(req: AgentCreateRequest, request: Request, db: Database = Depends(get_db)):
    require_admin(request, db)
    try:
        agent = AgentRegistry(db).create_agent(
            slug=req.slug, name=req.name,
            description=req.description, status=req.status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="operation could not be completed") from exc
    return {"agent": agent}


@app.patch("/api/agents/{slug}")
def api_agents_update(slug: str, req: AgentUpdateRequest, request: Request, db: Database = Depends(get_db)):
    require_admin(request, db)
    fields = {k: v for k, v in req.model_dump().items() if v is not None}
    agent = AgentRegistry(db).update_agent(slug, fields)
    if not agent:
        raise HTTPException(status_code=404, detail="agent not found")
    return {"agent": agent}


@app.post("/api/agents/{slug}/versions")
def api_agent_version_create(slug: str, req: AgentVersionCreateRequest,
                             request: Request, db: Database = Depends(get_db)):
    require_admin(request, db)
    reg = AgentRegistry(db)
    try:
        version_row = reg.create_version(
            slug=slug, version=req.version,
            instructions=req.instructions,
            model_provider=req.model_provider,
            model_name=req.model_name,
            thinking_effort=req.thinking_effort,
            tool_policy=req.tool_policy,
            output_schema=req.output_schema,
            status=req.status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="operation could not be completed") from exc
    activated = None
    if req.activate:
        activated = reg.set_active_version(slug, req.version)
    return {"version": version_row, "activated": activated}


@app.post("/api/agents/{slug}/versions/{version}/activate")
def api_agent_version_activate(slug: str, version: str, request: Request, db: Database = Depends(get_db)):
    require_admin(request, db)
    try:
        agent = AgentRegistry(db).set_active_version(slug, version)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="operation could not be completed") from exc
    return {"agent": agent}


@app.get("/api/agents/{slug}/active")
def api_agent_active(slug: str, db: Database = Depends(get_db)):
    payload = AgentRegistry(db).get_active_version(slug)
    if not payload:
        raise HTTPException(status_code=404, detail="no active version for agent")
    return payload


@app.post("/api/tools")
def api_tools_register(req: ToolRegisterRequest, request: Request, db: Database = Depends(get_db)):
    require_admin(request, db)
    tool = AgentRegistry(db).register_tool(
        name=req.name, description=req.description,
        input_schema=req.input_schema, output_schema=req.output_schema,
        scopes=req.scopes, requires_approval=req.requires_approval,
        enabled=req.enabled,
    )
    return {"tool": tool}


@app.post("/api/connections/register")
def api_connections_register(req: ConnectionRegisterRequest, request: Request, db: Database = Depends(get_db)):
    require_admin(request, db)
    conn = AgentRegistry(db).register_connection(
        connection_id=req.connection_id, provider=req.provider,
        kind=req.kind, base_url=req.base_url, status=req.status,
        metadata=req.metadata,
    )
    return {"connection": conn}


def _cache(db):
    from ..cache import CacheLayer
    from ..config import load_cache_policy

    return CacheLayer(db, load_cache_policy())


@app.get("/api/v1/providers")
@app.get("/providers")
def providers(db: Database = Depends(get_db)):
    router = Router(db, _cache(db), settings)
    return {"status": router.status_report(), "usage": router.usage_report()}


@app.post("/api/v1/benchmark/run")
@app.post("/benchmark/run")
def run_benchmark_endpoint(req: RunRequest, background: BackgroundTasks,
                           request: Request, db: Database = Depends(get_db)):
    require_admin(request, db)
    """Synchronous on purpose for V0: a live run takes minutes but the job row
    is updated continuously, so n8n can poll /jobs/{id} from a second workflow
    if needed."""
    from ..benchmark.run import run_benchmark
    from ..config import load_icp

    registry = AgentRegistry(db)
    run_id = registry.create_run("lead-generation", {
        "icp": req.icp, "seed_csv": req.seed_csv,
    })
    step_id = registry.start_step(run_id, "pipeline", input_data={"icp": req.icp})
    try:
        icp_payload: str | dict = req.icp
        if req.overrides:
            base = load_icp(req.icp)
            merged_limits = {**base.get("v0_limits", {}), **req.overrides.get("v0_limits", {})}
            icp_payload = {**base, "v0_limits": merged_limits}
        summary, metrics, outputs = run_benchmark(
            icp_payload, seed_csv=req.seed_csv, agent_run_id=run_id)
    except Exception as exc:
        registry.finish_step(step_id, "FAILED", error=f"{type(exc).__name__}: {exc}")
        registry.finish_run(run_id, "FAILED", error=f"{type(exc).__name__}: {exc}")
        raise HTTPException(status_code=500, detail="benchmark failed") from exc
    registry.finish_run(run_id, summary.get("state") or "COMPLETED", {
        "job_id": summary.get("job_id"), "metrics": metrics, "outputs": outputs,
    }, usage={
        "cost_usd": metrics.get("total_cost_usd", 0) if isinstance(metrics, dict) else 0,
        "prompt_tokens": metrics.get("prompt_tokens", 0) if isinstance(metrics, dict) else 0,
        "completion_tokens": metrics.get("completion_tokens", 0) if isinstance(metrics, dict) else 0,
    })
    registry.finish_step(step_id, "COMPLETED", output={"job_id": summary.get("job_id"), "state": summary.get("state")})
    return {
        "job_id": summary.get("job_id"),
        "agent_run_id": run_id,
        "state": summary.get("state"),
        "pause_reason": summary.get("pause_reason"),
        "metrics": metrics,
        "outputs": outputs,
    }


@app.get("/api/v1/jobs/{job_id}")
@app.get("/api/jobs/{job_id}")
@app.get("/jobs/{job_id}")
def get_job(job_id: str, db: Database = Depends(get_db)):
    org_clause, org_params = _org_clause(db)
    job = db.one(f"SELECT * FROM jobs WHERE job_id=?{org_clause}", (job_id, *org_params))
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    events = JobManager(db).events(job_id)
    return {"job": job, "events": events}


@app.get("/api/v1/jobs")
@app.get("/api/jobs")
@app.get("/jobs")
def list_jobs(db: Database = Depends(get_db)):
    clause, params = _org_clause(db)
    return db.query("SELECT job_id, icp_id, state, pause_reason, resume_at, created_at,"
                    f" updated_at FROM jobs WHERE 1=1{clause}"
                    " ORDER BY created_at DESC LIMIT 50", params)


@app.post("/api/v1/jobs/recover")
@app.post("/jobs/recover")
def recover_jobs(request: Request, db: Database = Depends(get_db)):
    require_admin(request, db)
    """Manual or maintenance trigger to recover stranded jobs left in active states."""
    from ..jobs import JobManager
    from ..queue import platform_mode, reclaim_expired

    reclaimed = reclaim_expired(db) if platform_mode() else 0
    recovered = JobManager(db).recover_interrupted_jobs()
    return {"recovered_jobs": recovered, "reclaimed_leases": reclaimed}


@app.post("/api/v1/jobs/drain-queued")
@app.post("/api/jobs/drain-queued")
def drain_queued_jobs(request: Request, db: Database = Depends(get_db)):
    require_admin(request, db)
    """Cancel all jobs stranded in QUEUED state with no worker to pick them up.
    Safe to call on Vercel / serverless deployments where platform_mode is False
    and no queue worker process exists.  Returns the list of cancelled job IDs."""
    from ..jobs import JobManager, QUEUED, CANCELLED
    from ..db import utcnow

    org_clause, org_params = _org_clause(db)
    rows = db.query(
        f"SELECT job_id, icp_id FROM jobs WHERE state=?{org_clause}",
        (QUEUED, *org_params),
    )
    cancelled = []
    jm = JobManager(db)
    for r in rows:
        try:
            jm.transition(r["job_id"], CANCELLED, "orphaned QUEUED job — no worker running (serverless drain)")
            cancelled.append(r["job_id"])
        except Exception:
            pass
    return {"drained": len(cancelled), "cancelled_job_ids": cancelled}


@app.post("/jobs/{job_id}/resume")
def resume_job(job_id: str, req: ResumeRequest, background: BackgroundTasks,
               request: Request, db: Database = Depends(get_db)):
    require_admin(request, db)
    from ..benchmark.run import run_benchmark as _run

    jobs = JobManager(db)
    org_clause, org_params = _org_clause(db)
    job = db.one(f"SELECT icp_id, state, params FROM jobs WHERE job_id=?{org_clause}",
                 (job_id, *org_params))
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if job["state"] != PAUSED:
        raise HTTPException(status_code=409, detail=f"job is {job['state']}, only PAUSED resumes")
    jobs.resume(job_id)
    from ..config import load_icp

    summary, metrics, outputs = _run(load_icp(job["icp_id"]), job_id=job_id)
    return {"state": summary.get("state"), "metrics": metrics}


# Columns returned by the leads LIST endpoint. `raw` (the full evidence blob,
# often several KB per row) is excluded unless asked for: the dashboard lists
# hundreds of rows and never reads it there — the detail/report paths do.
LEAD_LIST_COLUMNS = (
    "lead_id", "job_id", "name", "domain", "city", "country", "industry",
    "employee_count", "branches", "phone", "email", "email_status",
    "email_confidence", "decision_maker", "decision_maker_title", "linkedin",
    "website", "social", "qualification_score", "tier", "score", "stage",
    "processing_mode", "requires_review", "legal_decision", "sources",
    "created_at", "updated_at", "disposition", "disposition_note",
    "disposition_at", "decided_by",
)


@app.get("/api/v1/leads")
@app.get("/api/leads")
@app.get("/leads")
def leads(job_id: str | None = Query(default=None), stage: str | None = Query(default=None),
          limit: int = Query(default=100, ge=1, le=1000),
          offset: int = Query(default=0, ge=0),
          include_raw: bool = Query(default=False),
          db: Database = Depends(get_db)):
    columns = ", ".join(LEAD_LIST_COLUMNS)
    if include_raw:
        columns = "*"
    sql = f"SELECT {columns} FROM leads WHERE 1=1"
    params: list = []
    org_clause, org_params = _org_clause(db)
    sql += org_clause
    params.extend(org_params)
    if job_id:
        sql += " AND job_id=?"
        params.append(job_id)
    if stage:
        sql += " AND stage=?"
        params.append(stage)
    sql += " ORDER BY score DESC LIMIT ? OFFSET ?"
    params.extend((limit, offset))
    return db.query(sql, params)


@app.post("/api/v1/verify-email")
@app.post("/verify-email")
def verify_email(req: VerifyRequest, db: Database = Depends(get_db)):
    router = Router(db, _cache(db), settings)
    return VerificationPipeline(router).verify(req.email)


@app.get("/api/v1/report/{job_id}")
@app.get("/report/{job_id}")
def report(job_id: str, db: Database = Depends(get_db)):
    org_clause, org_params = _org_clause(db)
    job = db.one(f"SELECT icp_id, params FROM jobs WHERE job_id=?{org_clause}",
                 (job_id, *org_params))
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    leads = db.leads_for_job(job_id)
    metrics = None
    if job.get("params"):
        try:
            metrics = json.loads(job["params"]).get("metrics")
        except json.JSONDecodeError:
            pass
    if metrics is None:
        usage = db.query(
            f"SELECT units FROM usage_ledger WHERE job_id=?{_org_clause(db)[0]}",
            (job_id, *_org_clause(db)[1]))
        summary = {"job_id": job_id, "stages": {}}
        metrics = compute_metrics(summary, leads, usage)
    return {"job_id": job_id, "metrics": metrics,
            "report_markdown": render_report(metrics, {"stages": {}}, leads)}


@app.post("/api/v1/sync-supabase")
@app.post("/sync-supabase")
def sync_supabase(req: SyncRequest, request: Request, db: Database = Depends(get_db)):
    require_admin(request, db)
    from ..sync import SupabaseError, sync_job_to_supabase

    org_clause, org_params = _org_clause(db)
    job = db.one(f"SELECT state FROM jobs WHERE job_id=?{org_clause}",
                 (req.job_id, *org_params))
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if job["state"] not in ("COMPLETED", "DEGRADED"):
        raise HTTPException(status_code=409,
                            detail=f"job state is {job['state']}; sync needs COMPLETED/DEGRADED")
    try:
        return sync_job_to_supabase(db, req.job_id)
    except SupabaseError as exc:
        raise HTTPException(status_code=400, detail="supabase sync failed") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="supabase sync failed") from exc


# ---------------------------------------------------------------------------
# Chat — conversational agent that drives the engine (function calling)
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=16_384)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1, max_length=50)
    provider: str | None = Field(default=None, min_length=1, max_length=128)
    tools: list[str] | None = Field(default=None, max_length=32)
    agent: str | None = Field(default=None, min_length=1, max_length=128)


@app.post("/api/chat")
def api_chat(req: ChatRequest, db: Database = Depends(get_db)):
    from .chat import run_agent

    router = Router(db, _cache(db), settings)
    return run_agent(router, db, [message.dict() for message in req.messages], provider=req.provider,
                     enabled_tools=req.tools, agent_slug=req.agent)


# ---------------------------------------------------------------------------
# MCP server — stateless streamable-HTTP JSON-RPC at POST /mcp
# ---------------------------------------------------------------------------

@app.post("/mcp")
async def mcp_endpoint(request: Request, db: Database = Depends(get_db)):
    from .mcp import handle_jsonrpc

    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid JSON body") from exc
    payload, status = handle_jsonrpc(body, Router(db, _cache(db), settings), db)
    if payload is None:
        return Response(status_code=status)
    return JSONResponse(payload, status_code=status)


@app.get("/mcp")
def mcp_hint():
    return {
        "server": "lead-engine MCP",
        "transport": "streamable-http (stateless JSON-RPC 2.0)",
        "usage": "POST /mcp with JSON-RPC: initialize, tools/list, tools/call",
        "example": {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    }


# ---------------------------------------------------------------------------
# Dashboard admin API — consumed by the RTL control UI in /static
# ---------------------------------------------------------------------------

RUN_LOCK = threading.Lock()


_STATUS_TTL_SECONDS = 4
_status_cache: dict = {}  # per-org slots (bounded below)


@app.get("/api/status")
def api_status(db: Database = Depends(get_db)):
    """Everything the dashboard needs in one call: real registry state,
    real usage from the ledger, real job states, cache and leads counts.

    Short in-process cache: the dashboard polls this every few seconds and
    the aggregate runs ~a dozen queries; 4s staleness is invisible there
    but cuts DB pressure sharply."""
    import time

    cache_key = getattr(db, "org_id", None) or "shared"
    now = time.time()
    cached = _status_cache.get(cache_key)
    if cached and now - cached["at"] < _STATUS_TTL_SECONDS:
        return cached["data"]
    data = _build_status(db)
    _status_cache[cache_key] = {"at": now, "data": data}
    if len(_status_cache) > 8:  # bound memory across tenants
        _status_cache.pop(next(iter(_status_cache)))
    return data


def _build_status(db: Database) -> dict:
    """Everything the dashboard needs in ONE round-trip budget.

    The previous implementation ran a *separate* usage query per provider (an
    N+1). Against a remote Postgres (Supabase) that is 20+ network round trips
    per call — seconds of latency for a dashboard that polls it. Everything
    below is batched: one providers read, one grouped usage read, and the
    tenant predicate is computed once and reused instead of once per query.
    """
    registry = Registry(db)
    registry.seed_if_empty()
    org_clause, org_params = _org_clause(db)

    # ONE grouped query for every provider's ledger totals (was N queries).
    usage_by_provider = {
        r["provider"]: r for r in db.query(
            "SELECT provider, COUNT(*) AS calls, COALESCE(SUM(units),0) AS units,"
            " MAX(ts) AS last_used FROM usage_ledger"
            f" WHERE 1=1{org_clause} GROUP BY provider", org_params)
    }

    providers = []
    for row in registry.status_table():
        env = row["env_key"]
        usage = usage_by_provider.get(row["name"]) or {}
        providers.append({
            "name": row["name"], "task": row["task"], "type": row["type"],
            "priority": row["priority"], "status": row["status"],
            "status_reason": row["status_reason"], "cooldown_until": row["cooldown_until"],
            "key_env": env, "has_key": env is None or bool(os.environ.get(env)),
            "is_local": env is None,
            "quota_kind": row["quota_kind"], "quota_limit": row["quota_limit"],
            "quota_used": row["quota_used"] or 0, "period": row["period"],
            "rpm_limit": row["rpm_limit"],
            "base_url": row.get("base_url"), "model_name": row.get("model_name"),
            "calls": usage.get("calls", 0), "units": usage.get("units", 0),
            "last_used": usage.get("last_used"),
        })

    jobs_by_state = {
        r["state"]: r["n"] for r in db.query(
            f"SELECT state, COUNT(*) AS n FROM jobs WHERE 1=1{org_clause}"
            " GROUP BY state", org_params)
    }
    leads_by_stage = {
        r["stage"]: r["n"] for r in db.query(
            f"SELECT stage, COUNT(*) AS n FROM leads WHERE 1=1{org_clause}"
            " GROUP BY stage", org_params)
    }
    approval_clause = " AND organization_id = ?" if getattr(db, "org_id", None) else ""
    approval_params = ((getattr(db, "org_id", None),) if approval_clause else ())
    try:
        pending_approvals = db.one(
            f"SELECT COUNT(*) AS n FROM approvals WHERE status='PENDING'{approval_clause}",
            approval_params)["n"]
    except Exception:
        pending_approvals = 0  # platform table may not exist on a dev SQLite
    return {
        "version": __version__,
        "providers": providers,
        "jobs_by_state": jobs_by_state,
        "recent_jobs": db.query(
            "SELECT job_id, icp_id, state, pause_reason, resume_at, created_at, updated_at"
            f" FROM jobs WHERE 1=1{org_clause} ORDER BY created_at DESC LIMIT 12",
            org_params),
        "leads_total": sum(leads_by_stage.values()),
        "leads_by_stage": leads_by_stage,
        "pending_approvals": pending_approvals,
        "cache_entries": {r["level"]: r["n"] for r in
                          db.query("SELECT level, COUNT(*) AS n FROM cache GROUP BY level")},
        "usage_totals": db.query(
            "SELECT provider, task, COUNT(*) AS calls, COALESCE(SUM(units),0) AS units"
            f" FROM usage_ledger WHERE 1=1{org_clause}"
            " GROUP BY provider, task ORDER BY units DESC LIMIT 20", org_params),
        "system": {
            "db_path": str(DB_PATH),
            "supabase_configured": bool(os.environ.get("SUPABASE_URL")
                                        and os.environ.get("SUPABASE_SERVICE_KEY")),
            "python": sys.version.split()[0],
            "config_dir": str(CONFIG_DIR),
        },
    }


_LIVE_MAX_SECONDS = 600      # default bound for one stream (client reconnects)
_LIVE_MIN_INTERVAL = 1.0     # fastest tick we will ever do
_LIVE_ERROR_INTERVAL = 2.0   # calm-down after a failing tick (never tight-loop)


def _live_connection(db: Database) -> Database:
    """A fresh handle per stream tick.

    A long-lived stream must never pin one connection for its whole life, so we
    open a short-lived handle each tick and close it right after. The handle is
    derived from the request's db (same path / DSN / tenant), which also keeps
    tests pointed at their temp database instead of the dev one.
    """
    org_id = getattr(db, "org_id", None)
    if getattr(db, "dialect", "sqlite") == "postgres":
        return open_db(org_id)
    path = getattr(db, "path", None)
    if not path:
        return open_db(org_id)
    conn = Database(path)
    conn.org_id = org_id
    return conn


def _live_snapshot(db: Database) -> tuple[str, dict]:
    """Change-digest + the FULL dashboard payload (same shape as /api/status).

    Pushing the status payload — instead of a reduced "pulse" — is what makes
    the dashboard instant: a connected client writes every frame straight into
    its `status` cache, so pages render from cache with zero polling and no
    extra round trip. Returns (digest, payload); the digest covers the volatile
    figures only, so an idle dashboard costs a few indexed reads per tick and
    sends nothing over the wire.
    """
    import hashlib
    import time as _time

    payload = _build_status(db)
    payload["alerts"] = _live_alerts(payload)
    payload["ts"] = _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime())

    fingerprint = {
        "providers": [[p["name"], p["status"], p["quota_used"], p["calls"]]
                      for p in payload["providers"]],
        "jobs": payload["jobs_by_state"],
        "recent": [[j["job_id"], j["state"], j.get("updated_at") or j.get("created_at")]
                   for j in payload["recent_jobs"]],
        "stages": payload["leads_by_stage"],
        "usage": payload["usage_totals"],
        "approvals": payload.get("pending_approvals", 0),
    }
    digest = hashlib.sha1(
        json.dumps(fingerprint, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    return digest, payload


def _live_alerts(payload: dict) -> list[dict]:
    """Honest alerts derived from the same numbers the payload already carries."""
    alerts: list[dict] = []
    jobs_by_state = payload.get("jobs_by_state") or {}
    paused = jobs_by_state.get("PAUSED", 0)
    if paused:
        alerts.append({"level": "warn", "kind": "paused_jobs", "count": paused,
                       "message": f"{paused} مهمة متوقفة مؤقتًا"})
    failed = jobs_by_state.get("FAILED", 0)
    if failed:
        alerts.append({"level": "error", "kind": "failed_jobs", "count": failed,
                       "message": f"{failed} مهمة فاشلة تحتاج مراجعة"})
    review = (payload.get("leads_by_stage") or {}).get("REVIEW", 0)
    if review:
        alerts.append({"level": "info", "kind": "pending_review", "count": review,
                       "message": f"{review} عميل محتمل في انتظار المراجعة"})
    return alerts


@app.get("/api/v1/live/stream")
@app.get("/api/live/stream")
def api_live_stream(
    max_seconds: int = Query(default=_LIVE_MAX_SECONDS, ge=1, le=_LIVE_MAX_SECONDS),
    db: Database = Depends(get_db),
):
    """Server-sent events: the dashboard's single real-time channel.

    Contract (pinned by tests/test_live_stream.py + tests/test_live_api.py):
      * every frame carries the same payload as `GET /api/status`, so a
        connected dashboard renders instantly and never polls;
      * the stream is bounded by `max_seconds` (capped) — a stuck viewer can
        never pin a worker;
      * a client that cannot be scoped to an organization is refused instead of
        being shown platform-wide totals (fail closed);
      * a fresh DB handle is opened per tick and closed right after, so a
        long-lived viewer never pins a pooled connection.
    """
    import time as _time

    from fastapi.responses import StreamingResponse

    org_id = getattr(db, "org_id", None)
    bounded = max(1, min(int(max_seconds or _LIVE_MAX_SECONDS), _LIVE_MAX_SECONDS))
    headers = {
        "Cache-Control": "no-cache, no-transform",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",     # stop nginx/proxy buffering the stream
    }

    if str(org_id or "").startswith("__"):
        # Authenticated but tenant-less: never leak platform-wide aggregates.
        def _refuse():
            yield ('event: error\ndata: '
                   '{"error":"no organization context","code":"no_org"}\n\n')

        return StreamingResponse(_refuse(), media_type="text/event-stream",
                                 headers=headers)

    def event_stream():
        last_digest: str | None = None
        started = _time.time()
        try:
            while _time.time() - started < bounded:
                conn = None
                try:
                    conn = _live_connection(db)
                    digest, payload = _live_snapshot(conn)
                except Exception as exc:  # a bad tick must not kill the stream
                    yield ("event: error\ndata: "
                           + json.dumps({"error": f"{type(exc).__name__}: {exc}"})
                           + "\n\n")
                    _time.sleep(_LIVE_ERROR_INTERVAL)
                    continue
                finally:
                    if conn is not None:
                        try:
                            conn.close()
                        except Exception:
                            pass

                if digest != last_digest:
                    last_digest = digest
                    yield f"event: snapshot\ndata: {json.dumps(payload, default=str)}\n\n"
                else:
                    yield ": keep-alive\n\n"   # comment frame keeps proxies awake
                _time.sleep(_LIVE_MIN_INTERVAL)
        except GeneratorExit:                  # client went away
            return

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers=headers)




@app.get("/api/analytics")
def api_analytics(db: Database = Depends(get_db)):
    """Time-series analytics for the dashboard: leads per day, jobs per day,
    usage units per day — last 30 days.

    Short in-process cache (same pattern as /api/status): the range filter
    with date() grouping cannot use the indexes above on every poll, so a
    30s staleness budget keeps the page instant while the numbers stay fresh.
    """
    import datetime
    import time

    cache_key = (getattr(db, "org_id", None) or "shared", "analytics")
    now = time.time()
    cached = _status_cache.get(cache_key)
    if cached and now - cached["at"] < 30:
        return cached["data"]

    cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)
              ).strftime("%Y-%m-%d")

    org_clause, org_params = _org_clause(db)
    leads_over_time = db.query(
        f"""SELECT date(created_at) AS date, COUNT(*) AS count
           FROM leads WHERE created_at >= ?{org_clause} GROUP BY date(created_at)
           ORDER BY date ASC""",
        (cutoff, *org_params),
    )
    jobs_over_time = db.query(
        f"""SELECT date(created_at) AS date, COUNT(*) AS total,
                  SUM(CASE WHEN state='COMPLETED' THEN 1 ELSE 0 END) AS completed,
                  SUM(CASE WHEN state='PAUSED' THEN 1 ELSE 0 END) AS paused,
                  SUM(CASE WHEN state='FAILED' THEN 1 ELSE 0 END) AS failed
           FROM jobs WHERE created_at >= ?{org_clause} GROUP BY date(created_at)
           ORDER BY date ASC""",
        (cutoff, *org_params),
    )
    usage_over_time = db.query(
        f"""SELECT date(ts) AS date, COALESCE(SUM(units),0) AS units,
                  COUNT(*) AS calls
           FROM usage_ledger WHERE ts >= ?{org_clause} GROUP BY date(ts)
           ORDER BY date ASC""",
        (cutoff, *org_params),
    )
    data = {
        "leads_over_time": leads_over_time,
        "jobs_over_time": jobs_over_time,
        "usage_over_time": usage_over_time,
    }
    _status_cache[cache_key] = {"at": now, "data": data}
    if len(_status_cache) > 8:  # bound memory across tenants
        _status_cache.pop(next(iter(_status_cache)))
    return data


class ProviderStatusRequest(BaseModel):
    status: str  # active | disabled


class ProviderConfigRequest(BaseModel):
    base_url: str | None = None
    model_name: str | None = None


def _validate_provider_url(name: str, value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or not host or parsed.username or parsed.password:
        raise HTTPException(status_code=422, detail="base_url must be a valid http(s) URL without credentials")
    try:
        is_private_ip = ipaddress.ip_address(host).is_private
    except ValueError:
        is_private_ip = False
    local_allowed = name == "ollama" and host in {"localhost", "127.0.0.1", "::1"}
    if not local_allowed:
        if parsed.scheme != "https" or is_private_ip or host == "localhost":
            raise HTTPException(status_code=422, detail="custom provider URLs must use public HTTPS endpoints")
        from ..netguard import UnsafeTarget, assert_public_host

        try:
            # resolve DNS too: a hostname pointing at internal space must fail
            assert_public_host(host)
        except UnsafeTarget:
            raise HTTPException(status_code=422,
                                detail="custom provider URLs must use public HTTPS endpoints")
    return value.rstrip("/")


@app.put("/api/providers/{name}/{task}/config")
def api_provider_config(name: str, task: str, req: ProviderConfigRequest,
                        request: Request, db: Database = Depends(get_db)):
    require_admin(request, db)
    """Persist non-secret provider settings used by the dashboard and adapters."""
    base_url = _validate_provider_url(name, (req.base_url or "").strip() or None)
    model_name = (req.model_name or "").strip() or None
    if base_url and not (base_url.startswith("https://") or base_url.startswith("http://")):
        raise HTTPException(status_code=422, detail="base_url must start with http:// or https://")
    cur = db.execute(
        "UPDATE providers SET base_url=?, model_name=? WHERE name=? AND task=?",
        (base_url, model_name, name, task),
    )
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="provider/task pair not found")
    return {"ok": True, "name": name, "task": task, "base_url": base_url, "model_name": model_name}


@app.post("/api/providers/{name}/{task}/status")
def api_provider_status(name: str, task: str, req: ProviderStatusRequest,
                        request: Request, db: Database = Depends(get_db)):
    require_admin(request, db)
    if req.status not in ("active", "disabled"):
        raise HTTPException(status_code=422, detail="status must be active or disabled")
    if not Registry(db).mark(name, task, req.status, "manual control from dashboard"):
        raise HTTPException(status_code=404, detail="provider/task pair not found")
    return {"ok": True, "name": name, "task": task, "status": req.status}


@app.post("/api/providers/{name}/{task}/reset")
def api_provider_reset(name: str, task: str, request: Request, db: Database = Depends(get_db)):
    require_admin(request, db)
    """Clear quota usage + cooldown for a provider (e.g. after a monthly
    reset that the engine missed, or for testing)."""
    cur = db.execute(
        "UPDATE providers SET quota_used=0, status='active', status_reason=NULL,"
        " cooldown_until=NULL WHERE name=? AND task=?", (name, task))
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="provider/task pair not found")
    return {"ok": True, "name": name, "task": task}


@app.get("/api/config")
def api_config_list(request: Request, db: Database = Depends(get_db)):
    require_admin(request, db)
    out = {}
    for key, path in CONFIG_FILES.items():
        text = path.read_text(encoding="utf-8")
        parsed = None
        try:
            parsed = yaml.safe_load(text)
        except yaml.YAMLError:
            pass
        out[key] = {"path": str(path.relative_to(ROOT)), "text": text, "parsed": parsed}
    return out


def _deep_merge(base: dict, patch: dict) -> dict:
    """Recursively merge patch into a copy of base (patch wins on scalars)."""
    out = dict(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


@app.put("/api/config/{key}")
def api_config_update(key: str, req: dict, request: Request, db: Database = Depends(get_db)):
    require_admin(request, db)
    path = CONFIG_FILES.get(key)
    if not path:
        raise HTTPException(status_code=404, detail="unknown config key")
    values = req.get("values")
    if isinstance(values, dict):
        # Structured update from the friendly settings form: merge into the
        # existing YAML so untouched sections survive.
        try:
            current = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            current = {}
        text = yaml.safe_dump(_deep_merge(current, values),
                              allow_unicode=True, sort_keys=False)
    else:
        text = req.get("text")
        if not isinstance(text, str) or not text.strip():
            raise HTTPException(status_code=422, detail="text is required")
    try:
        yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail="YAML غير صالح") from exc
    try:
        backup = path.with_suffix(path.suffix + ".bak")
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail="الملفات للقراءة فقط في نشر السيرفرليس — عدّل الإعدادات محليًا أو من Vercel env",
        ) from exc
    global settings
    settings = load_settings()
    return {"ok": True, "key": key, "backup": str(backup.relative_to(ROOT))}


@app.post("/api/jobs/start")
def api_jobs_start(req: RunRequest, background: BackgroundTasks,
                   request: Request, db: Database = Depends(get_db)):
    require_admin(request, db)
    """Start a benchmark run in the background; the UI polls /jobs/{id}."""
    from ..config import load_icp

    try:
        load_icp(req.icp)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"ICP غير موجود: {req.icp}")
    with RUN_LOCK:  # one engine run at a time (sqlite + provider sanity)
        job_id = JobManager(db).create_job(req.icp)
    from ..queue import enqueue, platform_mode
    from ..entitlements import check_job_start

    org_id = getattr(db, "org_id", None)
    allowed, reason = check_job_start(db, org_id)
    if not allowed:
        raise HTTPException(status_code=429, detail=reason)
    if platform_mode():
        enqueue(db, job_id)  # the worker fleet executes it
    else:
        background.add_task(_run_background_job, req.icp, job_id, req.seed_csv)
    return {"job_id": job_id, "state": "QUEUED", "mode": "queue" if platform_mode() else "inline"}


def _run_background_job(icp_name: str, job_id: str, seed_csv: str | None):
    from ..benchmark.run import run_benchmark

    try:
        run_benchmark(icp_name, job_id=job_id, seed_csv=seed_csv)
    except Exception as exc:  # config/startup errors: mark FAILED, never hang
        db = open_db()
        JobManager(db).mark_failed(job_id, "background job failed")
        db.conn.close()


@app.post("/api/cache/purge")
def api_cache_purge(request: Request, db: Database = Depends(get_db)):
    require_admin(request, db)
    from ..cache import CacheLayer
    from ..config import load_cache_policy

    deleted = CacheLayer(db, load_cache_policy()).purge_expired()
    return {"purged": deleted}


@app.get("/api/export/leads.csv", include_in_schema=False)
def api_export_csv():
    path = OUTPUTS_DIR / "leads.csv"
    if not path.exists():
        raise HTTPException(status_code=404, detail="no leads.csv yet — run a benchmark first")
    return FileResponse(path, media_type="text/csv", filename="leads.csv")


# ---------------------------------------------------------------------------
# API keys — stored in .env (gitignored), applied to the running process
# immediately. Secrets are never returned to the browser, only masked chips.
# ---------------------------------------------------------------------------

ENV_PATH = ROOT / ".env"
KEY_FIELDS = [
    {"name": "TAVILY_API_KEY", "group": "search"},
    {"name": "BRAVE_SEARCH_API_KEY", "group": "search"},
    {"name": "EXA_API_KEY", "group": "search"},
    {"name": "GEMINI_API_KEY", "group": "llm"},
    {"name": "GROQ_API_KEY", "group": "llm"},
    {"name": "OPENROUTER_API_KEY", "group": "llm"},
    {"name": "APOLLO_API_KEY", "group": "data"},
    {"name": "PROSPEO_API_KEY", "group": "data"},
    {"name": "HUNTER_API_KEY", "group": "email"},
    {"name": "ABSTRACT_API_KEY", "group": "email"},
    {"name": "MILLIONVERIFIER_API_KEY", "group": "email"},
    {"name": "SUPABASE_URL", "group": "storage", "plain": True},
    {"name": "SUPABASE_SERVICE_KEY", "group": "storage"},
    {"name": "OLLAMA_BASE_URL", "group": "local", "plain": True},
]
KEY_GROUPS = {"search": "البحث", "llm": "النماذج اللغوية", "data": "بيانات الأشخاص والشركات",
              "email": "البريد", "storage": "التخزين (Supabase)", "local": "محلي (Ollama)"}


def _mask(value: str, plain: bool) -> str:
    if not value:
        return ""
    if plain:
        return value
    pool = [k for k in value.split(",") if k.strip()]
    if len(pool) > 1:
        return f"{len(pool)} مفاتيح — {pool[0][:8]}…{pool[-1][-3:]}"
    if len(value) <= 9:
        return "•••"
    return f"{value[:6]}…{value[-3:]}"


@app.get("/api/keys")
def api_keys_list():
    out = []
    for field in KEY_FIELDS:
        value = os.environ.get(field["name"], "")
        out.append({**field, "configured": bool(value),
                    "masked": _mask(value, field.get("plain", False))})
    return {"env_path": str(ENV_PATH), "groups": KEY_GROUPS, "keys": out}


@app.post("/api/keys")
def api_keys_save(req: dict, request: Request, db: Database = Depends(get_db)):
    require_admin(request, db)
    """Save provided keys to .env + activate them in the running process.
    Empty string clears a key. Response contains masked values only."""
    updates = {}
    for field in KEY_FIELDS:
        if field["name"] not in req:
            continue
        raw = str(req[field["name"]]).strip()
        if field.get("plain"):
            value = raw
        else:
            # multi-key paste: newlines/spaces become the comma pool separator
            value = ",".join(
                seg.strip() for seg in raw.replace("\r", "").replace("\n", ",").split(",")
                if seg.strip())
            bad = [seg for seg in value.split(",") if "=" in seg]
            if bad:
                raise HTTPException(status_code=422,
                                    detail=f"قيمة غير صالحة في {field['name']}: {bad[0][:30]}")
        updates[field["name"]] = value
    if not updates:
        raise HTTPException(status_code=422, detail="لا مفاتيح في الطلب")

    # Platform path: org-scoped AES-GCM credentials in the DB (source of
    # truth in production). .env remains the local bootstrap fallback.
    org_id = os.environ.get("LEAD_ENGINE_ORG_ID")
    platform_mode = bool(org_id and os.environ.get("LEAD_ENGINE_ENCRYPTION_KEY"))
    if platform_mode:
        from ..secrets import SecretsUnavailable, save_provider_credential

        try:
            for key, value in updates.items():
                save_provider_credential(db, org_id, key, value)
        except SecretsUnavailable:
            platform_mode = False

    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    remaining = dict(updates)
    out = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line and not line.strip().startswith("#") else None
        if key in remaining:
            value = remaining.pop(key)
            if value:                      # empty -> remove the line entirely
                out.append(f"{key}={value}")
        else:
            out.append(line)
    for key, value in remaining.items():
        if value:
            out.append(f"{key}={value}")
    if platform_mode:
        pass  # credentials persisted encrypted above; env hydrated below
    else:
        try:
            ENV_PATH.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail="مفيش .env قابل للكتابة في نشر السيرفرليس — حط المفاتيح في Vercel Project Settings → Environment Variables",
            ) from exc

    for key, value in updates.items():
        if value:
            os.environ[key] = value
        else:
            os.environ.pop(key, None)
    load_env()

    if platform_mode:
        from ..secrets import hydrate_environment

        hydrate_environment(db, org_id)

    # keys changed -> re-evaluate availability right away
    Registry(db).seed_if_empty()
    return {"ok": True, "saved": sorted(updates.keys()),
            "keys": api_keys_list()["keys"]}


# ---------------------------------------------------------------------------
# Per-key usage — real consumption (tokens where the provider reports them),
# quota percent vs the configured limit, live from the provider when it
# exposes a key-usage API (OpenRouter), else from the local ledger.
# ---------------------------------------------------------------------------

PROVIDER_DOCS = {
    "TAVILY_API_KEY": ("tavily", "https://app.tavily.com/home"),
    "BRAVE_SEARCH_API_KEY": ("brave", "https://api-dashboard.search.brave.com/app/keys"),
    "EXA_API_KEY": ("exa", "https://dashboard.exa.ai/api-keys"),
    "GEMINI_API_KEY": ("gemini", "https://aistudio.google.com/apikey"),
    "GROQ_API_KEY": ("groq", "https://console.groq.com/keys"),
    "OPENROUTER_API_KEY": ("openrouter", "https://openrouter.ai/settings/keys"),
    "APOLLO_API_KEY": ("apollo", "https://app.apollo.io/settings/integrations/api"),
    "PROSPEO_API_KEY": ("prospeo", "https://prospeo.io/api"),
    "HUNTER_API_KEY": ("hunter", "https://hunter.io/api-keys"),
    "ABSTRACT_API_KEY": ("abstract", "https://app.abstractapi.com/api/email-validation"),
    "MILLIONVERIFIER_API_KEY": ("millionverifier", "https://millionverifier.com/api"),
}


def _mask_key(key: str) -> str:
    return f"{key[:6]}…{key[-3:]}" if len(key) > 9 else "•••"


# Live provider credit/balance probes are outbound HTTP calls with 5–10s
# timeouts. They must never run inside a request the dashboard fires
# implicitly: they are opt-in (`?live=1`) and cached per key so a burst of
# viewers does not fan out one outbound call per request.
_LIVE_KEY_TTL_SECONDS = 120
_live_key_cache: dict[str, tuple[float, dict]] = {}


def _cached_key_live(probe, api_key: str) -> dict | None:
    import time

    now = time.time()
    hit = _live_key_cache.get(api_key)
    if hit and now - hit[0] < _LIVE_KEY_TTL_SECONDS:
        return hit[1]
    value = probe(api_key)
    _live_key_cache[api_key] = (now, value)
    while len(_live_key_cache) > 64:  # bound memory
        _live_key_cache.pop(next(iter(_live_key_cache)))
    return value



def _prospeo_key_live(api_key: str):
    try:
        import requests
        resp = requests.get(
            "https://api.prospeo.io/account-information",
            headers={"X-KEY": api_key}, timeout=5)
        if resp.status_code == 200:
            data = (resp.json() or {}).get("response") or {}
            remaining = data.get("remaining_credits")
            used = data.get("used_credits")
            total = (remaining or 0) + (used or 0)
            percent = round(100.0 * used / total, 1) if total else 0.0
            return {"usage_source": "provider", "used": used, "limit": total,
                    "remaining": remaining, "percent": percent}
    except Exception:
        pass
    return None


def _millionverifier_key_live(api_key: str):
    try:
        import requests
        resp = requests.get(
            f"https://api.millionverifier.com/api/v3/credits?api={api_key}",
            timeout=5)
        if resp.status_code == 200:
            data = resp.json() or {}
            credits = data.get("credits", 0)
            return {"usage_source": "provider", "used": 0, "limit": credits,
                    "remaining": credits, "percent": 0.0}
    except Exception:
        pass
    return None

def _openrouter_key_live(api_key: str):
    """Live credit usage straight from the provider for this key."""
    try:
        import requests
        resp = requests.get(
            "https://openrouter.ai/api/v1/auth/key",
            headers={"Authorization": f"Bearer {api_key}"}, timeout=10)
        if resp.status_code == 200:
            data = (resp.json() or {}).get("data") or {}
            usage = data.get("usage")
            limit = data.get("limit")
            percent = None
            if isinstance(limit, (int, float)) and limit and isinstance(usage, (int, float)):
                percent = round(100.0 * usage / limit, 1)
            return {"usage_source": "provider", "used": usage, "limit": limit,
                    "percent": percent}
    except Exception:
        pass
    return None


@app.get("/api/keys/usage")
def api_keys_usage(db: Database = Depends(get_db),
                   live_probe: bool = Query(default=False)):
    """Everything the keys page needs: per provider, per pooled key — calls,
    units, prompt/completion tokens, last used — plus quota percent.

    `live_probe` opts into outbound provider balance calls (OpenRouter /
    Prospeo / MillionVerifier, 5–10s timeouts each, cached 2 minutes). The
    dashboard must only pass it on the Keys page where the operator asked for
    it — never on an implicit poll.
    """
    org_clause, org_params = _org_clause(db)
    per_key_rows = db.query(
        f"SELECT provider, task, key_index, COUNT(*) AS calls,"
        " COALESCE(SUM(units),0) AS units,"
        " COALESCE(SUM(prompt_tokens),0) AS prompt_tokens,"
        " COALESCE(SUM(completion_tokens),0) AS completion_tokens,"
        f" MAX(ts) AS last_used FROM usage_ledger WHERE 1=1{org_clause}"
        " GROUP BY provider, task, key_index", org_params)
    status_by_pair = {(r["name"], r["task"]): r
                      for r in Registry(db).status_table()}
    usage_agg = db.query(
        f"SELECT provider, COUNT(*) AS calls, COALESCE(SUM(units),0) AS units,"
        " COALESCE(SUM(prompt_tokens),0) AS prompt_tokens,"
        f" COALESCE(SUM(completion_tokens),0) AS completion_tokens FROM usage_ledger"
        f" WHERE 1=1{org_clause} GROUP BY provider", org_params)
    agg_by_provider = {r["provider"]: r for r in usage_agg}

    # group ledger rows by provider (key_index may be NULL for legacy rows)
    by_provider: dict = {}
    for r in per_key_rows:
        by_provider.setdefault(r["provider"], []).append(r)

    env_by_provider = {}
    for env_key, (name, _docs) in PROVIDER_DOCS.items():
        raw = os.environ.get(env_key) or ""
        env_by_provider[name] = [k.strip() for k in raw.replace("\n", ",").split(",") if k.strip()]

    out = []
    for env_key, (name, docs) in PROVIDER_DOCS.items():
        keys_pool = env_by_provider.get(name) or []
        ledger_rows = by_provider.get(name) or []
        agg = agg_by_provider.get(name) or {}

        # per-key buckets: match on key_index when recorded, else one bucket
        key_cards = []
        total_pct_bases = []
        if keys_pool:
            for idx, key in enumerate(keys_pool):
                rows = [r for r in ledger_rows if (r["key_index"] if r["key_index"] is not None else 0) == idx]
                key_cards.append({
                    "index": idx, "masked": _mask_key(key),
                    "calls": sum(r["calls"] for r in rows),
                    "units": sum(r["units"] for r in rows),
                    "prompt_tokens": sum(r["prompt_tokens"] for r in rows),
                    "completion_tokens": sum(r["completion_tokens"] for r in rows),
                    "last_used": max((r["last_used"] for r in rows), default=None),
                })
        elif ledger_rows:
            key_cards.append({
                "index": None, "masked": None,
                "calls": agg.get("calls", 0), "units": agg.get("units", 0),
                "prompt_tokens": agg.get("prompt_tokens", 0),
                "completion_tokens": agg.get("completion_tokens", 0),
                "last_used": max((r["last_used"] for r in ledger_rows), default=None),
            })

        quota = {}
        first_status = None
        for pair, row in status_by_pair.items():
            if pair[0] == name:
                first_status = row
                if row["quota_limit"] is not None:
                    quota = {"kind": row["quota_kind"], "limit": row["quota_limit"],
                             "used": row["quota_used"] or 0,
                             "percent": round(100.0 * (row["quota_used"] or 0) / row["quota_limit"], 1)}
                else:
                    quota = {"kind": row["quota_kind"], "limit": None,
                             "used": row["quota_used"] or 0, "percent": None}
                break

        live = None
        if live_probe and keys_pool:
            probe = None
            if name == "openrouter":
                probe = _openrouter_key_live
            elif name == "prospeo":
                probe = _prospeo_key_live
            elif name == "millionverifier":
                probe = _millionverifier_key_live
            if probe is not None:
                live = _cached_key_live(probe, keys_pool[0])

        out.append({
            "provider": name, "env_key": env_key, "docs_url": docs,
            "keys_configured": len(keys_pool),
            "keys": key_cards,
            "usage": {"calls": agg.get("calls", 0), "units": agg.get("units", 0),
                      "prompt_tokens": agg.get("prompt_tokens", 0),
                      "completion_tokens": agg.get("completion_tokens", 0),
                      "total_tokens": (agg.get("prompt_tokens", 0) + agg.get("completion_tokens", 0))},
            "quota": quota,
            "live": live,
            "status": first_status["status"] if first_status else None,
        })

    totals = {"prompt_tokens": sum(o["usage"]["prompt_tokens"] for o in out),
              "completion_tokens": sum(o["usage"]["completion_tokens"] for o in out),
              "calls": sum(o["usage"]["calls"] for o in out)}
    return {"providers": out, "totals": totals}


@app.post("/api/data/reset")
def api_data_reset(request: Request, db: Database = Depends(get_db)):
    require_admin(request, db)
    """Wipe generated data (jobs, leads, evidence, cache, usage) for the
    CALLING tenant only. The provider registry is kept. With no tenant
    context (single-org dev), only unscoped rows are removed — never other
    tenants' data."""
    org_id = getattr(db, "org_id", None)
    scope = "WHERE organization_id = ?" if org_id else "WHERE organization_id IS NULL"
    params = (org_id,) if org_id else ()
    for table in ("leads", "evidence", "cache", "usage_ledger", "job_events", "jobs"):
        db.execute(f"DELETE FROM {table} {scope}", params)
    return {"ok": True, "scope": org_id or "unscoped"}


app.include_router(policy_router)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
# React build assets live under /assets/ (relative to root) for the modern
# dashboard served from the same origin as the API.
_ASSETS_DIR = ROOT / "lead_engine" / "static" / "assets"
if _ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=_ASSETS_DIR), name="assets")
_FAVICON = ROOT / "lead_engine" / "static" / "favicon.svg"
if _FAVICON.exists():
    @app.get("/favicon.svg", include_in_schema=False)
    def _favicon():
        return FileResponse(_FAVICON)


@app.get("/", include_in_schema=False)
def dashboard():
    resp = FileResponse(STATIC_DIR / "index.html")
    # Prevent aggressive caching of HTML so users always get the latest JS hash
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


# ===== Mount feature routers (added by multi-domain refactor) =====
from ..activity import get_router as _activity_router
app.include_router(_activity_router())

# Agentic research jobs (R2/R3) — chat-first persistent research
from .research_api import router as research_router
app.include_router(research_router)

# Stage 3 — human review board (R5): presentation + the four decisions
from .review_api import router as review_router
app.include_router(review_router)

# ICP versions — the user's filtering criteria (stage 2 gate)
from .icp_api import router as icp_router
app.include_router(icp_router)

# OAuth Integration Platform (Phase 2) — connect/callback/revoke per provider
from .integrations_api import router as integrations_router
from .events_api import router as events_router
from .data_api import router as data_router
from .platform_api import router as platform_router
from .pitch_api import router as pitch_router
app.include_router(integrations_router)
app.include_router(events_router)
app.include_router(data_router)
app.include_router(platform_router)
app.include_router(pitch_router)

# Observability (plan-improvement T3) — GET /metrics + GET /api/v1/slo.
# The in-process REGISTRY is already wired into _MetricsMiddleware above; this
# only exposes the read side (Prometheus text + the dashboard's SLO summary).
from .metrics_api import router as metrics_router
app.include_router(metrics_router)
# Billing (Stripe): checkout + signed webhook → organizations.limits.
# The webhook is intentionally public at the middleware (see admin_session_guard)
# and authenticates via the Stripe-Signature HMAC instead.
from .billing_api import router as billing_router
app.include_router(billing_router)
# NOTE: the live SSE stream is defined here in app.py (this module) — see
# api_live_stream. Never re-introduce a second route for /api/*/live/stream:
# the first registration wins and silently shadows the other implementation.


# SPA fallback — any non-API path that didn't match above returns the SPA
# index.html so the React Router (or any client router) can take over. This
# makes the dashboard work at /chat, /keys, /leads, etc. without 404s.
_API_PREFIXES = ("/api", "/mcp", "/static", "/jobs", "/leads", "/providers",
                 "/benchmark", "/report", "/sync-supabase", "/verify-email",
                 "/docs", "/openapi", "/redoc", "/health")


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    if any(full_path == p.strip("/") or full_path.startswith(p.strip("/") + "/")
           for p in _API_PREFIXES):
        raise HTTPException(status_code=404, detail="Not Found")
    index = STATIC_DIR / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="dashboard not built")
    resp = FileResponse(index)
    # Same no-cache for SPA routes so cached HTML never references dead JS
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp
