"""Chat agent tools + snippet contact extraction + ad-hoc ICP."""
import pytest

from lead_engine.api.chat import execute_tool, run_agent
from lead_engine.pipeline.icp import build_adhoc_icp
from lead_engine.pipeline.normalize import extract_contacts


class StubRouter:
    """Scripted router: returns queued function calls then a final text."""

    def __init__(self, script):
        self.script = list(script)
        self.payloads = []

    def route(self, task, payload, **kwargs):
        self.payloads.append(payload)
        step = self.script.pop(0) if self.script else {"text": "تم"}
        return {"text": step.get("text", ""), "function_calls": step.get("function_calls", [])}, \
               {"provider": "stub", "cached": False}

    def status_report(self):
        return [{"name": "gemini", "task": "reasoning", "status": "active",
                 "env_key": "GEMINI_API_KEY", "quota_used": 0, "quota_limit": None}]

    def usage_report(self):
        return []


class StubDb:
    def one(self, sql, params=()):
        return None

    def query(self, sql, params=()):
        return []


def test_extract_contacts_mobile_formats():
    for text in ["اتصل بنا 0501234567", "Call +966 50 123 4567", "هاتف: 0551234567"]:
        phones, email = extract_contacts(text)
        assert phones and phones[0].startswith("+9665"), text
        assert email is None


def test_extract_contacts_unified_and_landline():
    phones, _ = extract_contacts("موحد 920001234 أو 0126789012")
    assert "+966920001234" in phones or "+92001234" in [p for p in phones] or phones
    assert any(p.startswith("+9661") or p.startswith("+9200") for p in phones)


def test_extract_contacts_email_and_garbage_rejected():
    phones, email = extract_contacts("راسلنا info@clinic.com أو اتصل 12345")
    assert email == "info@clinic.com"
    assert phones == []          # 12345 is not a Saudi number


def test_adhoc_icp_riyadh_alias():
    icp = build_adhoc_icp(["الرياض"], "dental")
    assert icp["cities"] == [{"name": "Riyadh", "ar": "الرياض"}]
    assert icp["country"] == "SA"
    assert any("أسنان" in k for k in icp["keywords_ar"])
    plan_queries = [q["q"] for q in __import__("lead_engine.pipeline.icp", fromlist=["build_plan"]).build_plan(icp)["queries"]]
    assert any("Riyadh" in q for q in plan_queries)


def test_execute_tool_system_status():
    from lead_engine.db import Database

    db = Database(":memory:")
    out = execute_tool("system_status", {}, StubRouter([]), db)
    assert "providers" in out and "jobs" in out and "leads" in out


def test_execute_tool_unknown_is_honest():
    out = execute_tool("nope", {}, None, StubDb())
    assert "error" in out


def test_agent_executes_tool_and_replies():
    script = [
        {"function_calls": [{"name": "system_status", "args": {}}]},
        {"text": "النظام جاهز وكل حاجة شغالة."},
    ]
    router = StubRouter(script)
    result = run_agent(router, StubDb(), [{"role": "user", "content": "إيه الأخبار؟"}])
    assert result["reply"] == "النظام جاهز وكل حاجة شغالة."
    assert result["tools"][0]["name"] == "system_status"
    assert result["tools"][0]["ok"] is True
    # contents must have carried the tool response back to the model
    last = router.payloads[-1]["contents"][-1]
    assert last["parts"][0]["functionResponse"]["name"] == "system_status"


def test_agent_run_tool_with_mocked_pipeline(monkeypatch):
    """The full run_lead_generation tool path — pipeline mocked, no network."""
    import lead_engine.api.chat as chat_mod

    fake_summary = {"job_id": "job-x", "state": "COMPLETED", "leads": [
        {"name": "عيادة تجريبية", "city": "Riyadh", "domain": "x.sa", "phone": "+966501234567",
         "email": None, "tier": "A", "score": 70, "stage": "ACCEPTED", "website": "https://x.sa"}]}
    fake_metrics = {"discovery_raw_candidates": 5, "unique_after_dedup": 4,
                    "qualification_scored": 4, "final_leads": 1, "review_leads": 3,
                    "quota_units_total": 4, "total_cost_usd": 0}
    monkeypatch.setattr(chat_mod, "run_benchmark",
                        lambda *a, **k: (fake_summary, fake_metrics, {}))
    script = [
        {"function_calls": [{"name": "run_lead_generation",
                             "args": {"city": "الرياض", "industry": "dental"}}]},
        {"text": "جمعت لك 1 عيادة."},
    ]
    router = StubRouter(script)
    result = run_agent(router, StubDb(), [{"role": "user", "content": "اعمل ليد جينيراشن في الرياض"}])
    assert result["tools"][0]["ok"] is True
    assert result["reply"] == "جمعت لك 1 عيادة."
    response = router.payloads[-1]["contents"][-1]["parts"][0]["functionResponse"]["response"]
    assert response["accepted_leads"][0]["phone"] == "+966501234567"


def test_agent_unknown_tool_error_surfaces_to_model():
    script = [
        {"function_calls": [{"name": "nope", "args": {}}]},
        {"text": "الأداة مش موجودة."},
    ]
    router = StubRouter(script)
    result = run_agent(router, StubDb(), [{"role": "user", "content": "جرّب"}])
    assert result["tools"][0]["ok"] is False
    assert result["reply"] == "الأداة مش موجودة."
