"""OpenManus research runtime client — the agent's deep-browsing capability.

OpenManus runs as a SEPARATE service on infrastructure the operator controls
(currently the user's second machine) — it is outside this app's trust
boundary and keeps its own model keys. This client speaks the contract
documented in docs/openmanus-contract.md:

  POST {base}/tasks      {"type": "browse"|"research", "objective"?, "url"?,
                          "max_steps"?, "timeout_seconds"?}
                         -> {"task_id", "status"}
  GET  {base}/tasks/{id} -> {"task_id", "status": queued|running|completed|failed,
                             "result": {"summary", "url", "http_status", "title",
                                        "facts": [{"field","value","source_url",
                                                   "quote","inferred"}],
                                        "sources": [{"url","title","http_status"}]},
                             "error"}
  Auth: Authorization: Bearer $OPENMANUS_TOKEN

Honest degradation rules (directive §38): when the runtime is not configured
the caller gets UNAVAILABLE — never fabricated research. All facts coming
back keep their source_url so they enter the Truth Layer with provenance.
"""
import os
import time

import requests

POLL_INTERVAL_SECONDS = 2
DEFAULT_TASK_TIMEOUT_SECONDS = 240


def base_url() -> str | None:
    return (os.environ.get("OPENMANUS_BASE_URL") or "").rstrip("/") or None


def is_configured() -> bool:
    return bool(base_url())


def _headers() -> dict:
    token = os.environ.get("OPENMANUS_TOKEN") or ""
    return {"Authorization": f"Bearer {token}",
            "Content-Type": "application/json"} if token else {"Content-Type": "application/json"}


def submit_task(kind: str, *, objective: str | None = None,
                url: str | None = None, max_steps: int = 15,
                timeout_seconds: int = DEFAULT_TASK_TIMEOUT_SECONDS) -> dict:
    resp = requests.post(
        f"{base_url()}/tasks",
        json={"type": kind, "objective": objective, "url": url,
              "max_steps": max_steps, "timeout_seconds": timeout_seconds},
        headers=_headers(), timeout=15)
    resp.raise_for_status()
    return resp.json()


def poll_task(task_id: str, *, timeout_seconds: int = DEFAULT_TASK_TIMEOUT_SECONDS) -> dict:
    """Poll until terminal state or timeout. Returns the final status payload."""
    deadline = time.time() + timeout_seconds
    last = {}
    while time.time() < deadline:
        resp = requests.get(f"{base_url()}/tasks/{task_id}", headers=_headers(),
                            timeout=15)
        resp.raise_for_status()
        last = resp.json()
        if last.get("status") in ("completed", "failed"):
            return last
        time.sleep(POLL_INTERVAL_SECONDS)
    return {"task_id": task_id, "status": "timeout", "error": "runtime poll timeout"}


def research_company(router, db, subject_id: str, objective: str, *,
                     job_id: str | None = None,
                     timeout_seconds: int = DEFAULT_TASK_TIMEOUT_SECONDS) -> dict:
    """Deep-research one company and normalize the runtime result into
    fact-shaped records (field/value/source_url/quote) + visited sources."""
    try:
        submitted = submit_task("research", objective=f"{objective} (company: {subject_id})",
                                timeout_seconds=timeout_seconds)
        final = poll_task(submitted["task_id"], timeout_seconds=timeout_seconds + 10)
    except requests.RequestException as exc:
        return {"status": "UNAVAILABLE",
                "note": f"OpenManus runtime unreachable: {type(exc).__name__}"}
    if final.get("status") != "completed":
        return {"status": final.get("status", "failed").upper(),
                "note": final.get("error") or "runtime did not complete the task"}
    result = final.get("result") or {}
    facts = []
    for f in result.get("facts") or []:
        if not f.get("field") or f.get("value") in (None, ""):
            continue
        facts.append({"field": str(f["field"]), "value": str(f["value"]),
                      "source_url": f.get("source_url"), "quote": f.get("quote"),
                      "inferred": bool(f.get("inferred"))})
    return {
        "status": "COMPLETED",
        "summary": result.get("summary"),
        "url": result.get("url"),
        "http_status": result.get("http_status"),
        "title": result.get("title"),
        "facts": facts,
        "sources": result.get("sources") or [],
    }
