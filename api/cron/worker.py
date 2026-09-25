"""Vercel Cron entrypoint: one worker tick per invocation.

This is the durable-execution substrate production was missing (gap register
FRONT-03): vercel.json schedules this path, Vercel calls it with
`Authorization: Bearer $CRON_SECRET`, and the tick leases a queued job and
runs it to a terminal state. Raw ASGI on purpose — no framework import, so
the cold start of this lambda stays lean.

Filesystem functions are matched before rewrites on Vercel, so this handler
is reachable at /api/cron/worker even though a catch-all rewrite serves the
dashboard and API through api/index.py.
"""
import hmac
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


async def _json_response(send, status: int, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json; charset=utf-8")]})
    await send({"type": "http.response.body", "body": body})


async def handler(scope, receive, send) -> None:
    if scope.get("type") != "http":
        return
    secret = os.environ.get("CRON_SECRET") or ""
    auth = ""
    for key, value in scope.get("headers") or []:
        if key == b"authorization":
            auth = value.decode("latin-1")
            break
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    if not secret or not hmac.compare_digest(token, secret):
        await _json_response(send, 401, {"error": "unauthorized"})
        return

    from lead_engine.db import open_db
    from lead_engine.worker import run_worker_tick

    worker_id = f"cron-{os.environ.get('VERCEL_REGION', 'local')}"
    db = open_db()
    try:
        result = run_worker_tick(db, worker_id)
    except Exception as exc:  # the cron log needs a reason, not a stack dump
        await _json_response(send, 500, {"error": f"{type(exc).__name__}: {exc}"})
        return
    finally:
        db.close()
    await _json_response(send, 200, result)
