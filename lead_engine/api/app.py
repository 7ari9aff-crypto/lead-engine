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
import json
import ipaddress
import os
import sys
import threading
from urllib.parse import urlparse

import yaml
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import __version__
from ..benchmark.metrics import compute_metrics, render_report
from ..config import (
    CONFIG_DIR, DB_PATH, DATA_DIR, OUTPUTS_DIR, ROOT, load_env, load_settings,
)
from ..db import Database
from ..agent_registry import AgentRegistry
from ..jobs import PAUSED, JobManager
from ..providers.email import VerificationPipeline
from ..registry import Registry
from ..router import Router

load_env()
DATA_DIR.mkdir(exist_ok=True)
settings = load_settings()

STATIC_DIR = ROOT / "lead_engine" / "static"
CONFIG_FILES = {
    "settings": CONFIG_DIR / "settings.yaml",
    "cache_policy": CONFIG_DIR / "cache_policy.yaml",
    "icp_v0_saudi_dental": CONFIG_DIR / "icp" / "v0_saudi_dental.yaml",
    "legal_sa": CONFIG_DIR / "legal_policies" / "sa.yaml",
}

app = FastAPI(
    title="Lead Engine API",
    version=__version__,
    description="Quota-aware multi-provider lead generation engine "
                "(n8n = orchestration, FastAPI = brain, Supabase = storage)",
)

PROTECTED_PATHS = ("/api/", "/mcp", "/leads", "/jobs", "/providers", "/benchmark/",
                   "/sync-supabase", "/verify-email", "/report/", "/export/")


@app.middleware("http")
async def admin_session_guard(request: Request, call_next):
    from .auth import COOKIE_NAME, valid_session

    path = request.url.path
    public = path in {"/health", "/api/auth/login", "/api/auth/session", "/api/auth/logout"}
    protected = path.startswith(PROTECTED_PATHS)
    if protected and not public and not valid_session(request.cookies.get(COOKIE_NAME)):
        return JSONResponse({"detail": "authentication required"}, status_code=401)
    return await call_next(request)


def get_db():
    db = Database(DB_PATH)
    try:
        yield db
    finally:
        db.conn.close()


class RunRequest(BaseModel):
    icp: str = "v0_saudi_dental"
    seed_csv: str | None = None


class ResumeRequest(BaseModel):
    pass


class VerifyRequest(BaseModel):
    email: str


class SyncRequest(BaseModel):
    job_id: str
    stage: str = "ACCEPTED"


class AgentRunRequest(BaseModel):
    agent: str = "lead-generation"
    input: dict = Field(default_factory=dict)
    version: str | None = None


class ApprovalResolution(BaseModel):
    status: str


class LoginRequest(BaseModel):
    password: str


@app.post("/api/auth/login")
def auth_login(req: LoginRequest):
    from .auth import COOKIE_NAME, issue_session, password_matches

    if not password_matches(req.password):
        raise HTTPException(status_code=401, detail="invalid credentials")
    response = JSONResponse({"authenticated": True})
    response.set_cookie(COOKIE_NAME, issue_session(), httponly=True, samesite="lax",
                        secure=bool(os.environ.get("LEAD_ENGINE_COOKIE_SECURE")),
                        max_age=60 * 60 * 12)
    return response


@app.get("/api/auth/session")
def auth_session(request: Request):
    from .auth import COOKIE_NAME, enabled, valid_session

    return {"authenticated": not enabled() or valid_session(request.cookies.get(COOKIE_NAME))}


@app.post("/api/auth/logout")
def auth_logout():
    from .auth import COOKIE_NAME

    response = JSONResponse({"authenticated": False})
    response.delete_cookie(COOKIE_NAME)
    return response


@app.get("/health")
def health(db: Database = Depends(get_db)):
    router = Router(db, _cache(db), settings)
    providers = router.status_report()
    live = sorted({r["name"] for r in providers if r.get("has_key")})
    return {
        "status": "ok",
        "providers_configured": live,
        "note": "live provider pool depends on .env keys; missing keys are unavailable",
    }


@app.get("/api/agents")
def api_agents(db: Database = Depends(get_db)):
    return {"agents": AgentRegistry(db).agents()}


@app.get("/api/agents/{slug}/versions")
def api_agent_versions(slug: str, db: Database = Depends(get_db)):
    return {"versions": AgentRegistry(db).versions(slug)}


@app.post("/api/agent-runs")
def api_agent_run_create(req: AgentRunRequest, db: Database = Depends(get_db)):
    try:
        run_id = AgentRegistry(db).create_run(req.agent, req.input, req.version)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
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
def api_connection_check(provider: str, db: Database = Depends(get_db)):
    result = AgentRegistry(db).check_connection(provider)
    if not result:
        raise HTTPException(status_code=404, detail="provider connection not found")
    return result


@app.get("/api/approvals")
def api_approvals(status: str = "PENDING", db: Database = Depends(get_db)):
    return {"approvals": AgentRegistry(db).approvals(status)}


@app.post("/api/approvals/{approval_id}/resolve")
def api_approval_resolve(approval_id: str, req: ApprovalResolution,
                         db: Database = Depends(get_db)):
    if req.status not in ("APPROVED", "REJECTED"):
        raise HTTPException(status_code=422, detail="status must be APPROVED or REJECTED")
    if not AgentRegistry(db).resolve_approval(approval_id, req.status):
        raise HTTPException(status_code=404, detail="pending approval not found")
    return {"ok": True, "approval_id": approval_id, "status": req.status}


def _cache(db):
    from ..cache import CacheLayer
    from ..config import load_cache_policy

    return CacheLayer(db, load_cache_policy())


@app.get("/providers")
def providers(db: Database = Depends(get_db)):
    router = Router(db, _cache(db), settings)
    return {"status": router.status_report(), "usage": router.usage_report()}


@app.post("/benchmark/run")
def run_benchmark_endpoint(req: RunRequest, background: BackgroundTasks,
                           db: Database = Depends(get_db)):
    """Synchronous on purpose for V0: a live run takes minutes but the job row
    is updated continuously, so n8n can poll /jobs/{id} from a second workflow
    if needed."""
    from ..benchmark.run import run_benchmark

    registry = AgentRegistry(db)
    run_id = registry.create_run("lead-generation", {
        "icp": req.icp, "seed_csv": req.seed_csv,
    })
    step_id = registry.start_step(run_id, "pipeline", input_data={"icp": req.icp})
    try:
        summary, metrics, outputs = run_benchmark(
            req.icp, seed_csv=req.seed_csv, agent_run_id=run_id)
    except Exception as exc:  # surface config errors to the caller
        registry.finish_step(step_id, "FAILED", error=f"{type(exc).__name__}: {exc}")
        registry.finish_run(run_id, "FAILED", error=f"{type(exc).__name__}: {exc}")
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc
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


@app.get("/jobs")
def list_jobs(db: Database = Depends(get_db)):
    return db.query("SELECT job_id, icp_id, state, pause_reason, resume_at, created_at,"
                    " updated_at FROM jobs ORDER BY created_at DESC LIMIT 50")


@app.get("/jobs/{job_id}")
def get_job(job_id: str, db: Database = Depends(get_db)):
    job = db.one("SELECT * FROM jobs WHERE job_id=?", (job_id,))
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    events = JobManager(db).events(job_id)
    return {"job": job, "events": events}


@app.post("/jobs/{job_id}/resume")
def resume_job(job_id: str, req: ResumeRequest, background: BackgroundTasks,
               db: Database = Depends(get_db)):
    from ..benchmark.run import run_benchmark as _run

    jobs = JobManager(db)
    job = db.one("SELECT icp_id, state, params FROM jobs WHERE job_id=?", (job_id,))
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if job["state"] != PAUSED:
        raise HTTPException(status_code=409, detail=f"job is {job['state']}, only PAUSED resumes")
    jobs.resume(job_id)
    from ..config import load_icp

    summary, metrics, outputs = _run(load_icp(job["icp_id"]), job_id=job_id)
    return {"state": summary.get("state"), "metrics": metrics}


@app.get("/leads")
def leads(job_id: str | None = Query(default=None), stage: str | None = Query(default=None),
          limit: int = Query(default=100, ge=1, le=1000),
          offset: int = Query(default=0, ge=0),
          db: Database = Depends(get_db)):
    sql = "SELECT * FROM leads WHERE 1=1"
    params: list = []
    if job_id:
        sql += " AND job_id=?"
        params.append(job_id)
    if stage:
        sql += " AND stage=?"
        params.append(stage)
    sql += " ORDER BY score DESC LIMIT ? OFFSET ?"
    params.extend((limit, offset))
    return db.query(sql, params)


@app.post("/verify-email")
def verify_email(req: VerifyRequest, db: Database = Depends(get_db)):
    router = Router(db, _cache(db), settings)
    return VerificationPipeline(router).verify(req.email)


@app.get("/report/{job_id}")
def report(job_id: str, db: Database = Depends(get_db)):
    job = db.one("SELECT icp_id, params FROM jobs WHERE job_id=?", (job_id,))
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
        usage = db.query("SELECT units FROM usage_ledger WHERE job_id=?", (job_id,))
        summary = {"job_id": job_id, "stages": {}}
        metrics = compute_metrics(summary, leads, usage)
    return {"job_id": job_id, "metrics": metrics,
            "report_markdown": render_report(metrics, {"stages": {}}, leads)}


@app.post("/sync-supabase")
def sync_supabase(req: SyncRequest, db: Database = Depends(get_db)):
    from ..sync import SupabaseError, sync_job_to_supabase

    job = db.one("SELECT state FROM jobs WHERE job_id=?", (req.job_id,))
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if job["state"] not in ("COMPLETED", "DEGRADED"):
        raise HTTPException(status_code=409,
                            detail=f"job state is {job['state']}; sync needs COMPLETED/DEGRADED")
    try:
        return sync_job_to_supabase(db, req.job_id)
    except SupabaseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"supabase sync failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Chat — conversational agent that drives the engine (function calling)
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    messages: list  # [{role: user|assistant, content: str}]


@app.post("/api/chat")
def api_chat(req: ChatRequest, db: Database = Depends(get_db)):
    from .chat import run_agent

    if not req.messages:
        raise HTTPException(status_code=422, detail="messages is required")
    router = Router(db, _cache(db), settings)
    return run_agent(router, db, req.messages)


# ---------------------------------------------------------------------------
# MCP server — stateless streamable-HTTP JSON-RPC at POST /mcp
# ---------------------------------------------------------------------------

@app.post("/mcp")
async def mcp_endpoint(request: Request, db: Database = Depends(get_db)):
    from .mcp import handle_jsonrpc

    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid JSON body: {exc}") from exc
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


@app.get("/api/status")
def api_status(db: Database = Depends(get_db)):
    """Everything the dashboard needs in one call: real registry state,
    real usage from the ledger, real job states, cache and leads counts."""
    registry = Registry(db)
    registry.seed_if_empty()
    providers = []
    for row in registry.status_table():
        env = row["env_key"]
        usage = db.one(
            "SELECT COUNT(*) AS calls, COALESCE(SUM(units),0) AS units, MAX(ts) AS last_used"
            " FROM usage_ledger WHERE provider=?", (row["name"],))
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
            "calls": usage["calls"], "units": usage["units"], "last_used": usage["last_used"],
        })
    return {
        "version": __version__,
        "providers": providers,
        "jobs_by_state": {r["state"]: r["n"] for r in
                          db.query("SELECT state, COUNT(*) AS n FROM jobs GROUP BY state")},
        "recent_jobs": db.query(
            "SELECT job_id, icp_id, state, pause_reason, resume_at, created_at, updated_at"
            " FROM jobs ORDER BY created_at DESC LIMIT 12"),
        "leads_total": db.one("SELECT COUNT(*) AS n FROM leads")["n"],
        "leads_by_stage": {r["stage"]: r["n"] for r in
                           db.query("SELECT stage, COUNT(*) AS n FROM leads GROUP BY stage")},
        "cache_entries": {r["level"]: r["n"] for r in
                          db.query("SELECT level, COUNT(*) AS n FROM cache GROUP BY level")},
        "usage_totals": db.query(
            "SELECT provider, task, COUNT(*) AS calls, COALESCE(SUM(units),0) AS units"
            " FROM usage_ledger GROUP BY provider, task ORDER BY units DESC LIMIT 20"),
        "system": {
            "db_path": str(DB_PATH),
            "supabase_configured": bool(os.environ.get("SUPABASE_URL")
                                        and os.environ.get("SUPABASE_SERVICE_KEY")),
            "python": sys.version.split()[0],
            "config_dir": str(CONFIG_DIR),
        },
    }


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
    if not local_allowed and (parsed.scheme != "https" or is_private_ip or host == "localhost"):
        raise HTTPException(status_code=422, detail="custom provider URLs must use public HTTPS endpoints")
    return value.rstrip("/")


@app.put("/api/providers/{name}/{task}/config")
def api_provider_config(name: str, task: str, req: ProviderConfigRequest,
                        db: Database = Depends(get_db)):
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
                        db: Database = Depends(get_db)):
    if req.status not in ("active", "disabled"):
        raise HTTPException(status_code=422, detail="status must be active or disabled")
    if not Registry(db).mark(name, task, req.status, "manual control from dashboard"):
        raise HTTPException(status_code=404, detail="provider/task pair not found")
    return {"ok": True, "name": name, "task": task, "status": req.status}


@app.post("/api/providers/{name}/{task}/reset")
def api_provider_reset(name: str, task: str, db: Database = Depends(get_db)):
    """Clear quota usage + cooldown for a provider (e.g. after a monthly
    reset that the engine missed, or for testing)."""
    cur = db.execute(
        "UPDATE providers SET quota_used=0, status='active', status_reason=NULL,"
        " cooldown_until=NULL WHERE name=? AND task=?", (name, task))
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="provider/task pair not found")
    return {"ok": True, "name": name, "task": task}


@app.get("/api/config")
def api_config_list():
    out = {}
    for key, path in CONFIG_FILES.items():
        out[key] = {"path": str(path.relative_to(ROOT)), "text": path.read_text(encoding="utf-8")}
    return out


@app.put("/api/config/{key}")
def api_config_update(key: str, req: dict, db: Database = Depends(get_db)):
    path = CONFIG_FILES.get(key)
    if not path:
        raise HTTPException(status_code=404, detail="unknown config key")
    text = req.get("text")
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(status_code=422, detail="text is required")
    try:
        yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail=f"YAML غير صالح: {exc}") from exc
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
                   db: Database = Depends(get_db)):
    """Start a benchmark run in the background; the UI polls /jobs/{id}."""
    from ..config import load_icp

    try:
        load_icp(req.icp)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"ICP غير موجود: {req.icp}")
    with RUN_LOCK:  # one engine run at a time (sqlite + provider sanity)
        job_id = JobManager(db).create_job(req.icp)
    background.add_task(_run_background_job, req.icp, job_id, req.seed_csv)
    return {"job_id": job_id, "state": "QUEUED"}


def _run_background_job(icp_name: str, job_id: str, seed_csv: str | None):
    from ..benchmark.run import run_benchmark

    try:
        run_benchmark(icp_name, job_id=job_id, seed_csv=seed_csv)
    except Exception as exc:  # config/startup errors: mark FAILED, never hang
        db = Database(DB_PATH)
        JobManager(db).mark_failed(job_id, f"{type(exc).__name__}: {exc}")
        db.conn.close()


@app.post("/api/cache/purge")
def api_cache_purge(db: Database = Depends(get_db)):
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
    {"name": "HUNTER_API_KEY", "group": "email"},
    {"name": "ABSTRACT_API_KEY", "group": "email"},
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
def api_keys_save(req: dict, db: Database = Depends(get_db)):
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

    # keys changed -> re-evaluate availability right away
    Registry(db).seed_if_empty()
    return {"ok": True, "saved": sorted(updates.keys()),
            "keys": api_keys_list()["keys"]}


@app.post("/api/data/reset")
def api_data_reset(db: Database = Depends(get_db)):
    """Wipe all locally generated data (jobs, leads, evidence, cache, usage).
    The provider registry is kept."""
    for table in ("leads", "evidence", "cache", "usage_ledger", "job_events", "jobs"):
        db.execute(f"DELETE FROM {table}")
    return {"ok": True}


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
