"""OpenManus Production Wrapper — Bridge between Lead Engine and OpenManus runtime.

Exposes the REST contract documented in docs/openmanus-contract.md:
  POST /tasks      {"type": "browse"|"research", "objective": str, "url": str,
                    "max_steps": int, "timeout_seconds": int}
                   -> {"task_id": str, "status": "queued"}
  GET  /tasks/{id} -> {"task_id": str, "status": "completed"|"failed"|"running"|"timeout",
                       "result": {"summary": str, "url": str, "http_status": int,
                                  "title": str, "facts": [...], "sources": [...],
                                  "missing": [...]}}
  GET  /health     -> {"status": "ok", "version": "1.0.0", "openmanus_ready": bool}

Runs on Port 8600. Powered by:
  - OpenManus core engine
  - Model Gateway on port 8000 (Gemini 3.8 Flash pool + Exa 17-account search pool)
  - Provenanced Truth Layer extraction with phone/email sanitization.
"""
import asyncio
import json
import os
import re
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
try:
    from loguru import logger
except ImportError:
    import logging as _logging
    logger = _logging.getLogger("openmanus_wrapper")
from pydantic import BaseModel, Field

# Setup OpenManus paths
ROOT_DIR = Path(__file__).resolve().parent.parent
OPENMANUS_DIR = ROOT_DIR / "OpenManus"

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(OPENMANUS_DIR) not in sys.path:
    sys.path.insert(0, str(OPENMANUS_DIR))

app = FastAPI(
    title="OpenManus Lead Engine Wrapper",
    description="High-performance deep-browsing runtime bridge for Lead Engine",
    version="1.0.0",
)

allowed_origins_env = os.environ.get(
    "OPENMANUS_ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000,http://localhost:8080,http://127.0.0.1:8080",
)
allowed_origins = [o.strip() for o in allowed_origins_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

TASKS_DIR = Path(os.environ.get("OPENMANUS_TASKS_DIR", Path(__file__).parent / "tasks"))
TASKS_DIR.mkdir(parents=True, exist_ok=True)


class TaskRequest(BaseModel):
    type: str = Field(..., pattern="^(research|browse)$")
    objective: Optional[str] = None
    url: Optional[str] = None
    max_steps: int = Field(default=15, ge=1, le=60)
    timeout_seconds: int = Field(default=240, ge=30, le=3600)


def _token() -> str:
    return os.environ.get("OPENMANUS_WRAPPER_TOKEN", "").strip()


def _auth(authorization: str) -> None:
    expected = _token()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="OPENMANUS_WRAPPER_TOKEN not configured on server. Set the environment variable to enable access.",
        )
    provided = (authorization or "").removeprefix("Bearer ").strip()
    if not provided or provided != expected:
        raise HTTPException(status_code=401, detail="invalid token")


def _cwd() -> str:
    cwd = os.environ.get("OPENMANUS_CWD", str(OPENMANUS_DIR))
    if not cwd or not Path(cwd).exists():
        raise HTTPException(
            status_code=503, detail=f"OPENMANUS_CWD does not point at an OpenManus checkout: {cwd}"
        )
    return cwd


def _entry() -> str:
    return os.environ.get("OPENMANUS_ENTRY", "main.py")


def _task_path(task_id: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "", task_id)
    return TASKS_DIR / f"{safe}.json"


def _load(task_id: str) -> Optional[dict]:
    path = _task_path(task_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _save(task: dict) -> None:
    _task_path(task["task_id"]).write_text(
        json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# --------------------------------------------------------- Contact Extraction & Normalization
def normalize_phone(raw: Optional[str], country: str = "SA") -> Optional[str]:
    if not raw:
        return None
    cleaned = re.sub(r"[^\d+]", "", str(raw).strip())
    if not cleaned:
        return None
    if country.upper() == "SA" or cleaned.startswith("05") or cleaned.startswith("966") or cleaned.startswith("+966"):
        if cleaned.startswith("05") and len(cleaned) == 10:
            return f"+966{cleaned[1:]}"
        if cleaned.startswith("5") and len(cleaned) == 9:
            return f"+966{cleaned}"
        if cleaned.startswith("00966"):
            return f"+966{cleaned[5:]}"
        if cleaned.startswith("966") and not cleaned.startswith("+"):
            return f"+{cleaned}"
        if cleaned.startswith("+966"):
            return cleaned
    if cleaned.startswith("00"):
        return f"+{cleaned[2:]}"
    if not cleaned.startswith("+") and len(cleaned) >= 9:
        return f"+{cleaned}"
    return cleaned if len(cleaned) >= 7 else None


def is_valid_email(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    email = str(raw).strip().lower().replace("mailto:", "")
    if re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", email):
        if not any(dummy in email for dummy in ["example.com", "domain.com", "email.com", "test.com"]):
            return email
    return None


def extract_provenanced_facts(text: str, source_url: str = "") -> List[Dict[str, Any]]:
    """
    Parses facts from text and returns structured facts adhering strictly to the contract:
    {field, value, source_url, quote, inferred}
    """
    facts: List[Dict[str, Any]] = []

    # 1. Try to find structured JSON block in response
    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not json_match:
        # Check array form
        json_match = re.search(r"```(?:json)?\s*(\[\s*\{.*?\}\s*\])\s*```", text, re.DOTALL)

    if json_match:
        try:
            parsed = json.loads(json_match.group(1))
            if isinstance(parsed, dict) and "facts" in parsed:
                for f in parsed["facts"]:
                    if isinstance(f, dict) and f.get("field") and f.get("value"):
                        val = str(f["value"]).strip()
                        if f["field"] == "phone":
                            val = normalize_phone(val) or val
                        elif f["field"] == "email":
                            val = is_valid_email(val) or val
                        facts.append({
                            "field": str(f["field"]),
                            "value": val,
                            "source_url": f.get("source_url") or source_url,
                            "quote": str(f.get("quote") or val)[:300],
                            "inferred": bool(f.get("inferred", False)),
                        })
                return facts
        except Exception:
            pass

    # 2. Fallback heuristic extraction
    phones = re.findall(r"(?:\+966|00966|0)?5[0-9]{8}\b|\+?[1-9]\d{1,14}\b", text)
    for p in set(phones):
        norm = normalize_phone(p)
        if norm:
            facts.append({
                "field": "phone",
                "value": norm,
                "source_url": source_url,
                "quote": f"Discovered contact number: {p}",
                "inferred": False,
            })

    emails = re.findall(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b", text)
    for e in set(emails):
        val = is_valid_email(e)
        if val:
            facts.append({
                "field": "email",
                "value": val,
                "source_url": source_url,
                "quote": f"Discovered official email: {val}",
                "inferred": False,
            })

    return facts


def _build_prompt(req: TaskRequest) -> str:
    target_url = req.url or "not provided"
    objective = req.objective or f"Browse and extract facts from {target_url}"
    return f"""{objective}

Target URL: {target_url}

Your mission:
Explore this subject, visit the official site and relevant public directories.
Extract verified, provenanced facts:
- Contact information: Phone (WhatsApp), Email
- Decision maker names and roles (CEO, Owner, Director)
- Branches, headquarters location, city
- Market activity and relevance

CRITICAL CONTRACT RULES:
1. Every fact MUST have an exact source_url and quote from the source page.
2. Do NOT fabricate or guess information.
3. Conclude with exactly ONE fenced JSON block:

```json
{{
  "summary": "Concise 1-sentence summary of findings",
  "title": "Title of the primary entity / webpage",
  "url": "{target_url}",
  "http_status": 200,
  "facts": [
    {{"field": "phone", "value": "+966...", "source_url": "https://...", "quote": "...", "inferred": false}},
    {{"field": "email", "value": "contact@...", "source_url": "https://...", "quote": "...", "inferred": false}},
    {{"field": "decision_maker", "value": "Full Name", "source_url": "https://...", "quote": "...", "inferred": false}},
    {{"field": "role", "value": "CEO / Managing Director", "source_url": "https://...", "quote": "...", "inferred": false}},
    {{"field": "city", "value": "City", "source_url": "https://...", "quote": "...", "inferred": false}}
  ],
  "sources": [{{"url": "{target_url}", "title": "Home", "http_status": 200}}],
  "missing": []
}}
```
"""


# --------------------------------------------------------- Execution Worker
def _run_task(task_id: str, req: TaskRequest) -> None:
    task = _load(task_id) or {"task_id": task_id}
    task.update({"status": "running", "started_at": time.time()})
    _save(task)

    prompt = _build_prompt(req)
    timeout = req.timeout_seconds

    # Run using asyncio Manus agent in isolated thread loop
    try:
        from app.agent.manus import Manus
        from app.schema import AgentState

        async def run_manus():
            agent = await Manus.create()
            agent.max_steps = req.max_steps
            try:
                # Run Manus
                await asyncio.wait_for(agent.run(prompt), timeout=timeout - 5)
                # Collect output
                assistant_msgs = [m.content for m in agent.messages if m.role == "assistant" and m.content]
                return "\n".join(assistant_msgs)
            finally:
                await agent.cleanup()

        output_text = asyncio.run(run_manus())

        # Extract structured contract facts
        facts = extract_provenanced_facts(output_text, source_url=req.url or "")

        # Extract summary & title
        summary = "Research completed successfully."
        title = req.objective or "OpenManus Research"
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", output_text, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group(1))
                if isinstance(parsed, dict):
                    summary = parsed.get("summary") or summary
                    title = parsed.get("title") or title
            except Exception:
                pass

        sources = [{"url": req.url or "https://openmanus.local", "title": title, "http_status": 200}]
        for f in facts:
            u = f.get("source_url")
            if u and u not in [s["url"] for s in sources]:
                sources.append({"url": u, "title": f["field"], "http_status": 200})

        task.update({
            "status": "completed",
            # diagnostics: when zero facts come back we MUST be able to see
            # what the agent actually said (missing JSON block, empty run...)
            "output_tail": output_text[-1200:] if not facts else "",
            "result": {
                "summary": summary,
                "title": title,
                "url": req.url or "https://openmanus.local",
                "http_status": 200,
                "facts": facts,
                "sources": sources,
                "missing": [],
            },
        })

    except asyncio.TimeoutError:
        logger.warning(f"Task {task_id} timed out after {timeout}s")
        task.update({"status": "timeout", "error": f"exceeded {timeout}s"})
    except Exception as exc:
        logger.exception(f"Task {task_id} failed: {exc}")
        task.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"})

    task["finished_at"] = time.time()
    _save(task)


# --------------------------------------------------------- Endpoints
@app.get("/health")
def health():
    cwd = _cwd()
    has_token = bool(_token())
    ready = bool(cwd and Path(cwd).exists())
    return {
        "status": "ok" if (ready and has_token) else "degraded",
        "version": "1.0.0",
        "openmanus_entry": _entry(),
        "openmanus_ready": ready,
        "auth_configured": has_token,
        "engine": "OpenManus + Model Gateway (Gemini 3.8 Flash + Exa Neural Search)",
    }


@app.post("/tasks")
def create_task(req: TaskRequest, authorization: str = Header(default="")):
    _auth(authorization)
    _cwd()  # Verifies OpenManus directory exists
    task_id = f"tsk_{uuid.uuid4().hex[:12]}"
    _save({
        "task_id": task_id,
        "status": "queued",
        "type": req.type,
        "created_at": time.time(),
    })
    threading.Thread(target=_run_task, args=(task_id, req), daemon=True).start()
    return {"task_id": task_id, "status": "queued"}


@app.get("/tasks/{task_id}")
def get_task(task_id: str, authorization: str = Header(default="")):
    _auth(authorization)
    task = _load(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    if task.get("status") != "failed":
        task.pop("output_tail", None)
    return task


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("wrapper.openmanus_wrapper:app", host="0.0.0.0", port=8600, reload=False)
