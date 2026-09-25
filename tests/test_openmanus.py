"""R4 — OpenManus integration: REST client against the contract, the wrapper
service, and the honest-unavailable degradation rule."""
import json

import pytest
from fastapi.testclient import TestClient

from lead_engine.research import openmanus


# ------------------------------------------------------------ client tests
@pytest.fixture()
def runtime_env(monkeypatch):
    monkeypatch.setenv("OPENMANUS_BASE_URL", "https://openmanus.local")
    monkeypatch.setenv("OPENMANUS_TOKEN", "tok-123")


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def test_unconfigured_runtime_is_honest(monkeypatch):
    monkeypatch.setenv("OPENMANUS_BASE_URL", "")
    assert not openmanus.is_configured()
    result = openmanus.research_company(None, None, "clinic-c.com", "investigate")
    assert result["status"] == "UNAVAILABLE"
    assert "facts" not in result  # no fabricated research


def test_research_company_happy_path(runtime_env, monkeypatch):
    calls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append(url)
        return _FakeResponse({"task_id": "tsk_abc", "status": "queued"})

    def fake_get(url, headers=None, timeout=None):
        calls.append(url)
        return _FakeResponse({
            "task_id": "tsk_abc", "status": "completed",
            "result": {
                "summary": "عيادة بمقر واحد في جدة",
                "title": "Clinic C", "url": "https://clinic-c.com",
                "http_status": 200,
                "facts": [
                    {"field": "phone", "value": "+966501111111",
                     "source_url": "https://clinic-c.com/contact",
                     "quote": "call us", "inferred": False},
                    {"field": "branches", "value": "",
                     "source_url": "https://clinic-c.com", "inferred": False},
                ],
                "sources": [{"url": "https://clinic-c.com/contact", "title": "Contact",
                             "http_status": 200}],
            }})

    monkeypatch.setattr(openmanus.requests, "post", fake_post)
    monkeypatch.setattr(openmanus.requests, "get", fake_get)
    result = openmanus.research_company(None, None, "clinic-c.com", "investigate")
    assert result["status"] == "COMPLETED"
    assert "tasks" in calls[0] and "tsk_abc" in calls[1]
    # empty-valued facts are dropped, real ones keep provenance
    assert len(result["facts"]) == 1
    assert result["facts"][0]["source_url"] == "https://clinic-c.com/contact"


def test_runtime_failure_is_data_not_exception(runtime_env, monkeypatch):
    monkeypatch.setattr(openmanus.requests, "post",
                        lambda *a, **k: _FakeResponse({"task_id": "t1"}))
    monkeypatch.setattr(openmanus.requests, "get",
                        lambda *a, **k: _FakeResponse(
                            {"task_id": "t1", "status": "failed",
                             "error": "browser crashed"}))
    result = openmanus.research_company(None, None, "x.com", "obj")
    assert result["status"] == "FAILED"
    assert "browser crashed" in result["note"]


def test_runtime_unreachable_reports_unavailable(runtime_env, monkeypatch):
    import requests as _requests

    def boom(*a, **k):
        raise _requests.ConnectionError("no route to host")

    monkeypatch.setattr(openmanus.requests, "post", boom)
    result = openmanus.research_company(None, None, "x.com", "obj")
    assert result["status"] == "UNAVAILABLE"


# ------------------------------------------------------------ wrapper tests
@pytest.fixture()
def wrapper_client(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENMANUS_CWD", str(tmp_path / "OpenManus"))
    monkeypatch.setenv("OPENMANUS_ENTRY", "run_flow.py")
    monkeypatch.setenv("OPENMANUS_WRAPPER_TOKEN", "tok-123")
    monkeypatch.setenv("OPENMANUS_TASKS_DIR", str(tmp_path / "tasks"))
    (tmp_path / "OpenManus").mkdir()
    from wrapper import openmanus_wrapper as wrapper

    return TestClient(wrapper.app)


def test_wrapper_health(wrapper_client):
    body = wrapper_client.get("/health").json()
    assert body["status"] == "ok"
    assert body["openmanus_ready"] is True
    assert body["auth_configured"] is True


def test_wrapper_fails_closed_when_token_unset(wrapper_client, monkeypatch):
    monkeypatch.delenv("OPENMANUS_WRAPPER_TOKEN", raising=False)
    # Fail-closed: if token is unset on server, requests must fail with 503
    resp = wrapper_client.post(
        "/tasks", json={"type": "research"},
        headers={"Authorization": "Bearer any-token"})
    assert resp.status_code == 503
    assert "OPENMANUS_WRAPPER_TOKEN" in resp.json()["detail"]
    health = wrapper_client.get("/health").json()
    assert health["auth_configured"] is False
    assert health["status"] == "degraded" 


def test_wrapper_auth(wrapper_client):
    assert wrapper_client.post(
        "/tasks", json={"type": "research"},
        headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_wrapper_task_lifecycle_with_fake_openmanus(wrapper_client, tmp_path, monkeypatch):
    result_json = json.dumps({
        "summary": "عيادة في جدة بهاتف موثق",
        "title": "Clinic C", "url": "https://clinic-c.com", "http_status": 200,
        "facts": [{"field": "phone", "value": "+966501234567",
                   "source_url": "https://clinic-c.com/contact",
                   "quote": "call us", "inferred": False}],
        "sources": [{"url": "https://clinic-c.com", "title": "Home",
                     "http_status": 200}],
        "missing": ["email"],
    })
    fake_stdout = ("...agent logs...\n```json\n" + result_json + "\n```\n")

    class FakeProc:
        stdout = fake_stdout
        stderr = ""

    # the wrapper now runs the Manus agent IN-PROCESS — inject a fake
    # app.agent.manus module that "produces" the JSON result as an assistant
    # message, exercising the real extraction path
    import sys
    import types

    result_json_msg = ("```json\n" + result_json + "\n```")

    class FakeAgent:
        max_steps = 0
        messages = []
        @staticmethod
        async def create():
            return FakeAgent()
        async def run(self, prompt):
            class M:
                role, content = "assistant", result_json_msg
            FakeAgent.messages = [M()]
            captured["prompt"] = prompt
            return "done"
        async def cleanup(self):
            return None

    fake_manus = types.ModuleType("app.agent.manus")
    fake_manus.Manus = FakeAgent
    fake_schema = types.ModuleType("app.schema")
    class AgentState:
        pass
    fake_schema.AgentState = AgentState
    fake_pkg = types.ModuleType("app")
    fake_agent_pkg = types.ModuleType("app.agent")
    fake_pkg.agent = fake_agent_pkg
    fake_agent_pkg.manus = fake_manus
    monkeypatch.setitem(sys.modules, "app", fake_pkg)
    monkeypatch.setitem(sys.modules, "app.agent", fake_agent_pkg)
    monkeypatch.setitem(sys.modules, "app.agent.manus", fake_manus)
    monkeypatch.setitem(sys.modules, "app.schema", fake_schema)
    captured = {}
    headers = {"Authorization": "Bearer tok-123"}
    created = wrapper_client.post(
        "/tasks", json={"type": "research", "objective": "investigate clinic-c",
                        "timeout_seconds": 60}, headers=headers)
    assert created.status_code == 200
    task_id = created.json()["task_id"]
    # the thread completes fast with the fake subprocess — poll a few times
    final = None
    for _ in range(50):
        final = wrapper_client.get(f"/tasks/{task_id}", headers=headers).json()
        if final["status"] in ("completed", "failed", "timeout"):
            break
        import time

        time.sleep(0.05)
    assert final["status"] == "completed"
    assert final["result"]["facts"][0]["value"] == "+966501234567"
    assert "missing" in final["result"]
    # the research prompt (with the JSON-output instruction) reached the agent
    assert "facts" in captured["prompt"]


def test_wrapper_requires_configured_cwd(wrapper_client, monkeypatch, tmp_path):
    monkeypatch.setenv("OPENMANUS_CWD", str(tmp_path / "nope"))
    resp = wrapper_client.post("/tasks", json={"type": "research"},
                               headers={"Authorization": "Bearer tok-123"})
    assert resp.status_code == 503


# --------------------------------------------------------- extraction tests
def test_extract_provenanced_facts_prefers_fenced_block_and_normalizes():
    from wrapper.openmanus_wrapper import extract_provenanced_facts

    text = ('logs... ```json\n{"facts": ['
            '{"field": "phone", "value": "0501234567",'
            ' "source_url": "https://c.com", "quote": "call"},'
            '{"field": "email", "value": "BAD", "source_url": "https://c.com"}]}\n```')
    facts = extract_provenanced_facts(text, source_url="https://c.com")
    # phone normalized to E.164, invalid email dropped to the sanitized value
    assert facts[0]["value"] == "+966501234567"
    assert all(f["source_url"] for f in facts)
    assert extract_provenanced_facts("no json at all") == []
