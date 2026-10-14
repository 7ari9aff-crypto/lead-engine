"""Manus agent — reasoning/inference provider over the Manus v2 task API.

Manus is an agent service, not a raw chat-completions API: a task is created
asynchronously (POST /v2/task.create) and its result is polled (GET
/v2/task.listMessages). This adapter wraps that round trip behind the same
complete(prompt, json_mode) contract the other LLM adapters expose, so the
router and the research orchestrator use it exactly like Gemini/Groq.

Auth: the raw key in the `x-manus-api-key` header — no Bearer prefix (v2 docs).
Keys pool in MANUS_API_KEYS (comma-separated); base-class credit-aware
rotation moves off a key BEFORE it reaches its per-key daily budget, so a run
never stops to wait on a spent key.
"""
import json
import re
import time

from .base import (
    BaseProvider, ProviderAuthError, ProviderError, ProviderUnavailable,
    QuotaExhausted, RateLimited, random_local_part,
)

# Polling bounds: an agent task can take a minute or two; beyond that the
# caller is better served by the router trying the next provider.
POLL_TOTAL_SECONDS = 240
POLL_INTERVAL_SECONDS = 4
_FINAL_TYPES = ("assistant_message", "structured_output_result")


def _extract_final_text(messages) -> str:
    """Newest assistant-visible text out of a listMessages payload."""
    for msg in reversed(messages or []):
        mtype = msg.get("type") or ""
        if mtype not in _FINAL_TYPES:
            continue
        payload = msg.get(mtype) or {}
        candidate = payload.get("content") or payload.get("text")
        if candidate:
            return candidate if isinstance(candidate, str) else str(candidate)
    return ""


def _agent_status(messages) -> str | None:
    for msg in reversed(messages or []):
        if (msg.get("type") or "") == "status_update":
            status = (msg.get("status_update") or {}).get("agent_status")
            if status:
                return status
    return None


class ManusProvider(BaseProvider):
    name = "manus"
    ptype = "llm"
    tasks = ("reasoning", "inference")
    env_key = "MANUS_API_KEYS"
    # Credit-aware rotation: Manus grants each account ~300 daily credits;
    # the engine spends at most DEFAULT_KEY_BUDGET on one key before handing
    # work to the next (configured in settings.manus.daily_key_budget).
    daily_key_budget = 30.0
    key_budget_safety_margin = 2.0

    def __init__(self, settings: dict):
        super().__init__(settings)
        manus_cfg = (self.settings.get("manus", {}) or {})
        self.daily_key_budget = float(manus_cfg.get("daily_key_budget", self.daily_key_budget))
        self.key_budget_safety_margin = float(
            manus_cfg.get("key_budget_safety_margin", self.key_budget_safety_margin))
        self.agent_profile = manus_cfg.get("agent_profile", "standard")
        self.timeout = max(self.timeout, 120)  # agent tasks are not 30 s calls

    def _base_url(self) -> str:
        return (self.endpoint_url or "https://api.manus.ai").strip().rstrip("/")

    def _headers(self) -> dict:
        key = self.current_key()
        return {"x-manus-api-key": key or "", "Content-Type": "application/json"}

    def request(self, task: str, payload: dict) -> dict:
        prompt = payload["prompt"]
        json_mode = payload.get("json_mode", True)
        text, meta = self.complete(prompt, json_mode)
        return {"provider": self.name, "model": self.agent_profile, "text": text,
                "rate_info": meta.get("rate_info") or {},
                "usage": meta.get("usage") or {}, "units": 1}

    def complete(self, prompt: str, json_mode: bool):
        task_id = self._create_task(prompt, json_mode)
        text = self._await_result(task_id)
        if json_mode:
            text = _force_json(text)
        if self.configured_model_name:
            model = self.configured_model_name
        else:
            model = self.agent_profile
        return text or "", {"provider": self.name, "model": model}

    def _create_task(self, prompt: str, json_mode: bool) -> str:
        body = {
            "message": {"content": _agent_prompt(prompt, json_mode)},
            "agent_profile": self.agent_profile,
            "share_visibility": "private",
        }
        resp = self._http("POST", f"{self._base_url()}/v2/task.create",
                          json=body, headers=self._headers())
        data = self._json(resp)
        if not data.get("ok") or not data.get("task_id"):
            raise ProviderError(f"manus: task.create rejected: {str(data)[:200]}")
        return data["task_id"]

    def _await_result(self, task_id: str) -> str:
        deadline = time.time() + POLL_TOTAL_SECONDS
        terminal = None
        while time.time() < deadline:
            time.sleep(POLL_INTERVAL_SECONDS)
            try:
                mresp = self._http(
                    "GET", f"{self._base_url()}/v2/task.listMessages",
                    params={"task_id": task_id}, headers=self._headers())
            except ProviderUnavailable:
                continue  # transient poll failure: keep waiting
            mdata = self._json(mresp)
            messages = mdata.get("data") or []
            text = _extract_final_text(messages)
            if text:
                return text
            terminal = _agent_status(messages)
            if terminal in ("stopped", "error"):
                if terminal == "error":
                    raise ProviderError("manus: task ended with agent_status=error")
                break
        raise ProviderError(
            f"manus: no assistant content within {POLL_TOTAL_SECONDS}s"
            + (f" (last status: {terminal})" if terminal else ""))


def _agent_prompt(prompt: str, json_mode: bool) -> str:
    if json_mode:
        return (prompt + "\n\nAnswer ONLY with a single valid JSON object — "
                "no prose, no markdown fences.")
    return prompt


def _force_json(text: str) -> str:
    if text.strip().startswith("{"):
        return text.strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group(0) if match else text.strip()
