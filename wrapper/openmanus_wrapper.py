"""OpenManus Wrapper — deploy THIS on the machine that runs OpenManus.

It exposes the REST contract in docs/openmanus-contract.md on top of a stock
OpenManus checkout: each task becomes a subprocess run of `python <entry>`
with the prompt piped to stdin (OpenManus reads the prompt interactively via
input() — run_flow.py and main.py have no argparse), and the final stdout is
parsed for the last JSON block containing the structured facts.

OpenManus keeps its OWN LLM keys in its config/config.toml; this wrapper
holds only the shared bearer token. Tasks are tracked on disk (tasks/*.json)
so a wrapper restart does not lose running/completed work.

Run:
    export OPENMANUS_CWD=/path/to/OpenManus
    export OPENMANUS_ENTRY=run_flow.py            # or main.py
    export OPENMANUS_WRAPPER_TOKEN=<secret>
    uvicorn openmanus_wrapper:app --host 0.0.0.0 --port 8600
"""
import json
import os
import re
import subprocess
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="OpenManus Wrapper", version="1.0.0")

TASKS_DIR = Path(os.environ.get("OPENMANUS_TASKS_DIR", Path(__file__).parent / "tasks"))
TASKS_DIR.mkdir(parents=True, exist_ok=True)

RESEARCH_PROMPT_TEMPLATE = """{objective}

مهمتك: تصفح مصادر هذا الموضوع (ابدأ من الرابط المعطى إن وجد)، واجمع الحقائق
المهمة فقط: معلومات الاتصال (هاتف/إيميل)، عدد الفروع، صاحب القرار ومنصبه،
النشاط التسويقي، وأي دليل على ملاءمة الشركة.

قواعد صارمة:
- كل حقيقة لازم يكون معاها رابط المصدر اللي جبتها منه حرفيًا.
- ممنوع تخمين أرقام أو إيميلات. لو مش موجود اكتبه في missing — لا تختلق.
- في نهاية عملك أعد كتلة JSON واحدة (```json ... ```) بهذا الشكل بالظبط:

```json
{{
  "summary": "سطر واحد يلخص النتيجة",
  "title": "عنوان الصفحة الرئيسية اللي بدأت منها",
  "url": "{url}",
  "http_status": 200,
  "facts": [
    {{"field": "phone", "value": "+966...", "source_url": "https://...",
     "quote": "الجملة الحرفية من المصدر", "inferred": false}}
  ],
  "sources": [{{"url": "https://...", "title": "...", "http_status": 200}}],
  "missing": ["email"]
}}
```
"""


class TaskRequest(BaseModel):
    type: str = Field(..., pattern="^(research|browse)$")
    objective: str | None = None
    url: str | None = None
    max_steps: int = Field(default=15, ge=1, le=60)
    timeout_seconds: int = Field(default=240, ge=30, le=3300)


def _token() -> str:
    return os.environ.get("OPENMANUS_WRAPPER_TOKEN", "")


def _auth(authorization: str) -> None:
    expected = _token()
    if not expected:
        raise HTTPException(status_code=503, detail="OPENMANUS_WRAPPER_TOKEN not set")
    provided = (authorization or "").removeprefix("Bearer ").strip()
    if provided != expected:
        raise HTTPException(status_code=401, detail="invalid token")


def _cwd() -> str:
    cwd = os.environ.get("OPENMANUS_CWD")
    if not cwd or not Path(cwd).exists():
        raise HTTPException(status_code=503, detail="OPENMANUS_CWD does not point at an OpenManus checkout")
    return cwd


def _entry() -> str:
    return os.environ.get("OPENMANUS_ENTRY", "run_flow.py")


def _task_path(task_id: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "", task_id)
    return TASKS_DIR / f"{safe}.json"


def _load(task_id: str) -> dict | None:
    path = _task_path(task_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _save(task: dict) -> None:
    _task_path(task["task_id"]).write_text(
        json.dumps(task, ensure_ascii=False), encoding="utf-8")


def _build_prompt(req: TaskRequest) -> str:
    return RESEARCH_PROMPT_TEMPLATE.format(
        objective=req.objective or f"Browse and extract facts from {req.url}",
        url=req.url or "not provided")


def _extract_last_json(stdout: str) -> dict | None:
    """The last fenced ```json block wins; fall back to the last balanced
    object that contains a 'facts' key."""
    fenced = re.findall(r"```json\s*(\{.*?\})\s*```", stdout, re.DOTALL)
    for blob in reversed(fenced):
        try:
            data = json.loads(blob)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue
    for match in reversed(list(re.finditer(r"\{", stdout))):
        depth, start = 0, match.start()
        for i in range(start, len(stdout)):
            if stdout[i] == "{":
                depth += 1
            elif stdout[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        data = json.loads(stdout[start:i + 1])
                    except json.JSONDecodeError:
                        break
                    if isinstance(data, dict) and "facts" in data:
                        return data
                    break
        else:
            continue
    return None


def _run_task(task_id: str, req: TaskRequest) -> None:
    task = _load(task_id) or {"task_id": task_id}
    task.update({"status": "running", "started_at": time.time()})
    _save(task)
    prompt = _build_prompt(req)
    try:
        proc = subprocess.run(
            [os.environ.get("OPENMANUS_PYTHON", "python"), _entry()],
            input=prompt, cwd=_cwd(), capture_output=True, text=True,
            timeout=req.timeout_seconds)
        output = proc.stdout or ""
        data = _extract_last_json(output)
        if data is None:
            task.update({"status": "failed", "error":
                         "no result JSON in OpenManus output",
                         "output_tail": output[-800:]})
        else:
            facts = [f for f in (data.get("facts") or [])
                     if isinstance(f, dict) and f.get("field")
                     and f.get("value") not in (None, "")]
            task.update({
                "status": "completed",
                "result": {
                    "summary": data.get("summary"),
                    "title": data.get("title"),
                    "url": data.get("url") or req.url,
                    "http_status": data.get("http_status"),
                    "facts": facts,
                    "sources": [s for s in (data.get("sources") or [])
                                if isinstance(s, dict) and s.get("url")],
                    "missing": data.get("missing") or [],
                }})
    except subprocess.TimeoutExpired:
        task.update({"status": "timeout",
                     "error": f"exceeded {req.timeout_seconds}s"})
    except Exception as exc:  # noqa: BLE001 — a task failure is data, not a crash
        task.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
    task["finished_at"] = time.time()
    _save(task)


@app.get("/health")
def health():
    cwd = os.environ.get("OPENMANUS_CWD")
    return {"status": "ok", "version": "1.0.0",
            "openmanus_entry": _entry(),
            "openmanus_ready": bool(cwd and Path(cwd).exists())}


@app.post("/tasks")
def create_task(req: TaskRequest, authorization: str = Header(default="")):
    _auth(authorization)
    _cwd()  # fail fast when OpenManus is not installed here
    task_id = f"tsk_{uuid.uuid4().hex[:12]}"
    _save({"task_id": task_id, "status": "queued", "type": req.type,
           "created_at": time.time()})
    threading.Thread(target=_run_task, args=(task_id, req), daemon=True).start()
    return {"task_id": task_id, "status": "queued"}


@app.get("/tasks/{task_id}")
def get_task(task_id: str, authorization: str = Header(default="")):
    _auth(authorization)
    task = _load(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    if task.get("status") != "failed":
        task.pop("output_tail", None)  # raw logs only travel on failure
    return task
