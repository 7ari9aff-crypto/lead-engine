"""FastAPI layer — the engine as an HTTP service.

This is the piece n8n talks to:
  POST /benchmark/run      run the V0 pipeline (dry-run or live)
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
import os
import sys
import threading

import yaml
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import __version__
from ..benchmark.metrics import compute_metrics, render_report
from ..config import CONFIG_DIR, DB_PATH, DATA_DIR, ROOT, load_env, load_settings
from ..db import Database
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


def get_db():
    db = Database(DB_PATH)
    try:
        yield db
    finally:
        db.conn.close()


class RunRequest(BaseModel):
    icp: str = "v0_saudi_dental"
    dry_run: bool = Field(default=True, description="true = fixtures, no network")
    seed_csv: str | None = None


class ResumeRequest(BaseModel):
    dry_run: bool = False


class VerifyRequest(BaseModel):
    email: str
    dry_run: bool = False


class SyncRequest(BaseModel):
    job_id: str
    stage: str = "ACCEPTED"


@app.get("/health")
def health(db: Database = Depends(get_db)):
    router = Router(db, _cache(db), settings, dry_run=True)
    providers = router.status_report()
    return {
        "status": "ok",
        "providers_configured": sorted({r["name"] for r in providers}),
        "note": "dry_run adapter set is always available; live pool depends on .env keys",
    }


def _cache(db):
    from ..cache import CacheLayer
    from ..config import load_cache_policy

    return CacheLayer(db, load_cache_policy())


@app.get("/providers")
def providers(db: Database = Depends(get_db)):
    router = Router(db, _cache(db), settings, dry_run=True)
    return {"status": router.status_report(), "usage": router.usage_report()}


@app.post("/benchmark/run")
def run_benchmark_endpoint(req: RunRequest, background: BackgroundTasks):
    """Synchronous on purpose for V0: dry-run takes seconds; a live run takes
    minutes but the job row is updated continuously, so n8n can poll
    /jobs/{id} from a second workflow if needed."""
    from ..benchmark.run import run_benchmark

    try:
        summary, metrics, outputs = run_benchmark(
            req.icp, dry_run=req.dry_run, seed_csv=req.seed_csv)
    except Exception as exc:  # surface config errors to the caller
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc
    return {
        "job_id": summary.get("job_id"),
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

    # resume in the mode the job originally ran (dry-run flag is persisted)
    dry_run = req.dry_run
    try:
        stored = json.loads(job["params"] or "{}")
        if "dry_run" in stored:
            dry_run = bool(stored["dry_run"])
    except json.JSONDecodeError:
        pass
    summary, metrics, outputs = _run(load_icp(job["icp_id"]), dry_run=dry_run,
                                     job_id=job_id)
    return {"state": summary.get("state"), "metrics": metrics}


@app.get("/leads")
def leads(job_id: str | None = Query(default=None), stage: str | None = Query(default=None),
          db: Database = Depends(get_db)):
    sql = "SELECT * FROM leads WHERE 1=1"
    params: list = []
    if job_id:
        sql += " AND job_id=?"
        params.append(job_id)
    if stage:
        sql += " AND stage=?"
        params.append(stage)
    return db.query(sql + " ORDER BY score DESC", params)


@app.post("/verify-email")
def verify_email(req: VerifyRequest, db: Database = Depends(get_db)):
    router = Router(db, _cache(db), settings, dry_run=req.dry_run)
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
        summary = {"job_id": job_id, "stages": {}, "dry_run": False}
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


@app.post("/api/providers/{name}/{task}/status")
def api_provider_status(name: str, task: str, req: ProviderStatusRequest,
                        db: Database = Depends(get_db)):
    if req.status not in ("active", "disabled"):
        raise HTTPException(status_code=422, detail="status must be active or disabled")
    Registry(db).mark(name, task, req.status, "manual control from dashboard")
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
    backup = path.with_suffix(path.suffix + ".bak")
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    path.write_text(text, encoding="utf-8")
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
        job_id = JobManager(db).create_job(req.icp, {"dry_run": req.dry_run})
    background.add_task(_run_background_job, req.icp, req.dry_run, job_id, req.seed_csv)
    return {"job_id": job_id, "state": "QUEUED"}


def _run_background_job(icp_name: str, dry_run: bool, job_id: str, seed_csv: str | None):
    from ..benchmark.run import run_benchmark

    try:
        run_benchmark(icp_name, dry_run=dry_run, job_id=job_id, seed_csv=seed_csv)
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
    path = DATA_DIR.parent / "outputs" / "leads.csv"
    if not path.exists():
        raise HTTPException(status_code=404, detail="no leads.csv yet — run a benchmark first")
    return FileResponse(path, media_type="text/csv", filename="leads.csv")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(STATIC_DIR / "index.html")
