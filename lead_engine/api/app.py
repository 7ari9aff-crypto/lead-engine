"""FastAPI layer — the engine as an HTTP service.

This is the piece n8n talks to:
  POST /benchmark/run      run the V0 pipeline (dry-run or live)
  GET  /jobs/{job_id}      job state + stage summary (COMPLETED / PAUSED / ...)
  POST /jobs/{id}/resume   resume a PAUSED job
  GET  /leads              exported leads (filter by job/stage)
  POST /sync-supabase      push leads into the Supabase lead database
  POST /verify-email       5-state email verification
  GET  /providers          registry status + usage
"""
import json

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from ..benchmark.metrics import compute_metrics, render_report
from ..config import DB_PATH, DATA_DIR, load_env, load_settings
from ..db import Database
from ..jobs import PAUSED, JobManager
from ..providers.email import VerificationPipeline
from ..router import Router

load_env()
DATA_DIR.mkdir(exist_ok=True)
settings = load_settings()

app = FastAPI(
    title="Lead Engine API",
    version="0.1.0",
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
    job = db.one("SELECT icp_id, state FROM jobs WHERE job_id=?", (job_id,))
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if job["state"] != PAUSED:
        raise HTTPException(status_code=409, detail=f"job is {job['state']}, only PAUSED resumes")
    jobs.resume(job_id)
    from ..config import load_icp

    summary, metrics, outputs = _run(load_icp(job["icp_id"]), dry_run=req.dry_run,
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
