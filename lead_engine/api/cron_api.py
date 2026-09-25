"""Worker-tick HTTP surface: GET /api/cron/worker.

One invocation = one scheduling step (reclaim expired leases, reap stale agent
runs, lease and drive one job, flush the outbox, run the retention sweep). The
scheduler caller — Vercel is unavailable on this plan, so it is
`.github/workflows/worker-tick.yml` — authenticates with a dedicated bearer
secret, NOT a session: `CRON_SECRET` is verified here, in constant time, and
the path is exempt from the session middleware for the same reason the Stripe
webhook is (see `admin_session_guard`). Missing `CRON_SECRET` rejects every
call, so an unconfigured platform cannot drive the queue.

It lives on the app rather than in a sibling Vercel function file because the
FastAPI preset routes every path to `api/index.py`: a filesystem function at
the same path is never reached, and the 401 it appeared to return was the
middleware answering on its behalf.
"""
import hmac
import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(tags=["worker"])


def _bearer(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    return auth[7:].strip() if auth.lower().startswith("bearer ") else ""


@router.get("/api/cron/worker")
async def worker_tick(request: Request):
    secret = os.environ.get("CRON_SECRET") or ""
    if not secret or not hmac.compare_digest(_bearer(request), secret):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    from ..db import open_db
    from ..worker import run_worker_tick

    worker_id = f"cron-{os.environ.get('VERCEL_REGION', 'local')}"
    db = open_db()
    try:
        result = run_worker_tick(db, worker_id)
    except Exception as exc:  # the scheduler log needs a reason, not a stack
        return JSONResponse({"error": f"{type(exc).__name__}: {exc}"},
                            status_code=500)
    finally:
        db.close()
    return result
