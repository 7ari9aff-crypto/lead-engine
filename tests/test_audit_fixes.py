"""Regression tests for the 2026-10-20 audit (work/AUDIT_REPORT.md)."""
import pytest

from lead_engine import queue
from lead_engine.db import open_db
from lead_engine.jobs import JobManager


@pytest.fixture
def db(tmp_path, monkeypatch):
    from lead_engine import db as db_module
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "t.db")
    d = open_db()
    yield d
    d.close()


# ---- C1/C2: research-phase jobs with an expired lease must be reclaimed
@pytest.mark.parametrize("phase", ["DISCOVERING", "RESEARCHING", "VERIFYING", "QUALIFYING"])
def test_reclaim_expired_covers_research_phases(db, phase):
    jm = JobManager(db)
    j = jm.create_job("icp-x")
    queue.lease_next(db, "w1", 600)
    jm.transition(j, phase, "x")
    db.execute("UPDATE jobs SET lease_expires_at='2026-01-01T00:00:00Z' WHERE job_id=?", (j,))
    assert queue.reclaim_expired(db) == 1
    assert jm.current(j) == "QUEUED"


def test_reclaim_ignores_live_lease_in_research_phase(db):
    jm = JobManager(db)
    j = jm.create_job("icp-x")
    queue.lease_next(db, "w1", 600)
    jm.transition(j, "DISCOVERING", "x")
    assert queue.reclaim_expired(db) == 0
    assert jm.current(j) == "DISCOVERING"


# ---- A1: verified user with NO membership must not ride the bridge org
BRIDGE = "11111111-1111-1111-1111-111111111111"


def _make_members_table(db, rows=()):
    """Emulate Postgres' public schema on SQLite so the real query runs."""
    db.conn.execute("ATTACH DATABASE ':memory:' AS public")
    db.conn.execute("CREATE TABLE public.organization_members"
                    " (user_id TEXT, organization_id TEXT, role TEXT, created_at TEXT)")
    for r in rows:
        db.conn.execute("INSERT INTO public.organization_members VALUES (?,?,?,?)", r)


def _req(sub):
    from types import SimpleNamespace
    return SimpleNamespace(state=SimpleNamespace(claims={"sub": sub}))


def test_no_membership_fails_closed_when_membership_table_exists(db, monkeypatch):
    from lead_engine import tenant
    monkeypatch.setenv("LEAD_ENGINE_ORG_ID", BRIDGE)
    _make_members_table(db)
    tenant.apply_context(db, _req("stranger"))
    assert db.org_id == "__no_org__"


def test_member_resolves_to_own_org(db, monkeypatch):
    from lead_engine import tenant
    monkeypatch.setenv("LEAD_ENGINE_ORG_ID", BRIDGE)
    _make_members_table(db, [("u1", "org-u1", "owner", "2026-01-01")])
    tenant.apply_context(db, _req("u1"))
    assert db.org_id == "org-u1"


def test_bridge_still_used_when_no_membership_table(db, monkeypatch):
    """Ephemeral single-org SQLite deployments keep working (documented design)."""
    from lead_engine import tenant
    monkeypatch.setenv("LEAD_ENGINE_ORG_ID", BRIDGE)
    tenant.apply_context(db, _req("anyone"))
    assert db.org_id == BRIDGE


def test_get_db_dependency_matches_tenant_policy(db, monkeypatch):
    from lead_engine.api import app as app_module
    monkeypatch.setenv("LEAD_ENGINE_ORG_ID", BRIDGE)
    monkeypatch.setattr(app_module, "open_db", lambda *a, **k: db)
    _make_members_table(db)
    gen = app_module.get_db(_req("stranger"))
    handle = next(gen)
    assert handle.org_id == "__no_org__"


# ---- E1/E2: provider API keys must never reach error text
SECRET = "AIzaSyFAKEKEY_1234567890abcdef"


def _provider(monkeypatch, name="gemini"):
    from lead_engine.providers import llm
    monkeypatch.setenv("GEMINI_API_KEY", SECRET)
    cls = next(c for n, c in vars(llm).items()
               if isinstance(c, type) and getattr(c, "name", None) == name)
    return cls({})


def test_connection_error_text_does_not_contain_key(monkeypatch):
    import requests
    from lead_engine.router import ProviderUnavailable
    p = _provider(monkeypatch)

    def boom(self, method, url, **kw):
        raise requests.ConnectionError(f"HTTPConnectionPool: Max retries with url: /m?key={SECRET}")
    monkeypatch.setattr(requests.Session, "request", boom)
    with pytest.raises(ProviderUnavailable) as ei:
        p._http("POST", "https://x.invalid/m", json={})
    assert SECRET not in str(ei.value)


def test_http_error_body_does_not_contain_key(monkeypatch):
    import requests
    from lead_engine.router import ProviderError
    p = _provider(monkeypatch)

    class R:
        status_code = 400
        headers = {}
        text = f"bad request for key {SECRET}"
    monkeypatch.setattr(requests.Session, "request", lambda self, m, u, **kw: R())
    with pytest.raises(ProviderError) as ei:
        p._http("POST", "https://x.invalid/m", json={})
    assert SECRET not in str(ei.value)


def test_gemini_sends_key_in_header_not_url(monkeypatch):
    import requests
    p = _provider(monkeypatch)
    seen = {}

    class R:
        status_code = 200
        headers = {}
        def json(self): return {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}

    def fake(self, method, url, **kw):
        seen["url"], seen["headers"] = url, kw.get("headers") or {}
        return R()
    monkeypatch.setattr(requests.Session, "request", fake)
    p._generate([{"role": "user", "parts": [{"text": "hi"}]}])
    assert SECRET not in seen["url"]
    assert seen["headers"].get("x-goog-api-key") == SECRET


# ---- D2: phone normalisation
@pytest.mark.parametrize("raw", [
    "+966112345678", "00966112345678", "00 966 11 234 5678",
    "0112345678", "011 234 5678", "966112345678",
    "+966١١٢٣٤٥٦٧٨", "٠١١٢٣٤٥٦٧٨",
])
def test_saudi_landline_forms_normalise_identically(raw):
    from lead_engine.pipeline.normalize import normalize_phone
    assert normalize_phone(raw, "SA") == "+966112345678"


@pytest.mark.parametrize("raw", ["0501234567", "+966501234567", "00966501234567", "966501234567"])
def test_saudi_mobile_forms_normalise_identically(raw):
    from lead_engine.pipeline.normalize import normalize_phone
    assert normalize_phone(raw, "SA") == "+966501234567"


def test_normalise_keeps_foreign_numbers_intact():
    from lead_engine.pipeline.normalize import normalize_phone
    assert normalize_phone("+20 100 123 4567", "SA") == "+201001234567"
    assert normalize_phone("0020 100 123 4567", "SA") == "+201001234567"


# ---- D1/D2: dedup
C = dict(city="Riyadh", country="SA")


def _dedup(leads):
    from lead_engine.pipeline.dedup import DedupEngine
    return DedupEngine({}).run(leads)


def test_shared_phone_with_different_domains_not_merged():
    out, _ = _dedup([dict(name="Smile Dental", domain="smile.sa", phone="+966112345678", **C),
                     dict(name="Pearl Dental", domain="pearl.sa", phone="+966112345678", **C)])
    assert len(out) == 2


def test_shared_email_with_different_domains_not_merged():
    out, _ = _dedup([dict(name="A Clinic", domain="a.sa", email="info@group.sa", **C),
                     dict(name="B Clinic", domain="b.sa", email="info@group.sa", **C)])
    assert len(out) == 2


def test_transitive_chain_across_three_domains_not_merged():
    out, _ = _dedup([dict(name="A", domain="a.sa", phone="+966111111111", **C),
                     dict(name="B", domain="b.sa", phone="+966111111111", email="x@y.sa", **C),
                     dict(name="C", domain="c.sa", email="x@y.sa", **C)])
    assert len(out) == 3


def test_same_domain_still_merges():
    out, st = _dedup([dict(name="Smile Dental", domain="smile.sa", **C),
                      dict(name="Smile Dental Clinic", domain="smile.sa", phone="+966112345678", **C)])
    assert len(out) == 1 and st.merged_count == 1


def test_same_phone_one_side_without_domain_merges():
    out, _ = _dedup([dict(name="Smile Dental", domain="smile.sa", **C),
                     dict(name="Smile Dental Riyadh", domain=None, phone="0112345678", **C)])
    out2, _ = _dedup([dict(name="Smile Dental", domain="smile.sa", phone="+966112345678", **C),
                      dict(name="Smile Dental Riyadh", domain=None, phone="0112345678", **C)])
    assert len(out2) == 1


def test_local_and_international_phone_forms_dedupe():
    out, _ = _dedup([dict(name="Alpha", domain=None, phone="0501234567", **C),
                     dict(name="Beta Totally Different", domain=None, phone="+966501234567", **C)])
    assert len(out) == 1


def test_dedup_never_outputs_a_group_spanning_two_domains():
    """Property check: random leads sharing phones/emails/names across domains."""
    import random
    from lead_engine.pipeline.dedup import DedupEngine
    rng = random.Random(7)
    phones = ["+966111111111", "0111111111", "+966122222222", None]
    emails = ["info@g.sa", "x@y.sa", None]
    names = ["Smile Dental", "Smile Dental Clinic", "Pearl", "Al Amal", "عيادة الأمل"]
    for _ in range(200):
        leads = [dict(lead_id=f"L{n}", name=rng.choice(names),
                      domain=rng.choice(["a.sa", "b.sa", "c.sa", None]),
                      phone=rng.choice(phones), email=rng.choice(emails), **C)
                 for n in range(rng.randint(2, 8))]
        out, _ = DedupEngine({}).run(leads)
        for rec in out:
            doms = {x["domain"] for x in leads
                    if x["lead_id"] in rec["source_ids"] and x["domain"]}
            assert len(doms) <= 1


# ---- D3: an INVALID email must never yield an ACCEPTED lead
def _stage(lead):
    from lead_engine.pipeline.orchestrator import decide_stage
    return decide_stage(lead, {"storage_allowed": True, "requires_review": False})


def test_invalid_email_blocks_acceptance():
    assert _stage({"qualification_score": 95, "email": "bad@x.sa", "email_status": "INVALID"}) == "REVIEW"


def test_invalid_email_sets_review_flag_reason():
    lead = {"qualification_score": 95, "email": "bad@x.sa", "email_status": "INVALID"}
    _stage(lead)
    assert lead.get("requires_review") is True


@pytest.mark.parametrize("status", ["DELIVERABLE", "RISKY", "CATCH_ALL", "UNKNOWN", None])
def test_other_email_statuses_do_not_block_acceptance(status):
    assert _stage({"qualification_score": 95, "email": "a@x.sa", "email_status": status}) == "ACCEPTED"


def test_storage_not_allowed_still_rejects():
    from lead_engine.pipeline.orchestrator import decide_stage
    assert decide_stage({"qualification_score": 95}, {"storage_allowed": False, "requires_review": False}) == "REJECTED"


def test_low_score_goes_to_review():
    assert _stage({"qualification_score": 10}) == "REVIEW"


# ---- A2: the shared machine token must not be root
MACHINE = "machine-token-for-tests-0123456789"


@pytest.fixture
def machine_client(db, monkeypatch, tmp_path):
    """TestClient with EVERY filesystem write target redirected to tmp_path.
    These tests hit routes that write config/.env; if the guard ever regresses
    a failing test must not overwrite real repo files (it did once)."""
    from fastapi.testclient import TestClient
    from lead_engine.api import app as app_module
    sandbox_cfg = {}
    for key, path in app_module.CONFIG_FILES.items():
        copy = tmp_path / path.name
        copy.write_text(path.read_text(encoding="utf-8") if path.exists() else "", encoding="utf-8")
        sandbox_cfg[key] = copy
    monkeypatch.setattr(app_module, "CONFIG_FILES", sandbox_cfg)
    monkeypatch.setattr(app_module, "ENV_PATH", tmp_path / ".env")
    monkeypatch.setenv("LEAD_ENGINE_MCP_TOKEN", MACHINE)
    monkeypatch.setenv("LEAD_ENGINE_DEV_OPEN", "0")
    monkeypatch.setattr(app_module, "open_db", lambda *a, **k: db)
    monkeypatch.setattr("lead_engine.api.auth_jwt.auth_mode", lambda: "supabase")
    return TestClient(app_module.app, raise_server_exceptions=False)


H = {"Authorization": f"Bearer {MACHINE}"}


# (method, path, valid body) -- bodies must pass FastAPI validation so the
# request actually reaches the require_admin guard instead of 422-ing first.
SENSITIVE = [
    ("GET", "/api/keys", {}), ("POST", "/api/keys", {"keys": {"X": "y"}}),
    ("GET", "/api/config", {}), ("PUT", "/api/config/settings", {"text": "a: 1"}),
    ("POST", "/api/cache/purge", {}), ("POST", "/api/data/reset", {}),
    ("POST", "/api/privacy/erase", {"subject": "a@b.sa"}),
    ("GET", "/api/code/workspace", {}), ("GET", "/api/code/file?path=README.md", {}),
    ("POST", "/api/agents", {"slug": "aa", "name": "A"}),
    ("POST", "/api/tools", {"name": "t"}),
    ("POST", "/api/connections/register", {"connection_id": "cc", "provider": "p"}),
    ("PUT", "/api/providers/p/t/config", {}),
]


@pytest.mark.parametrize("method,path,body", SENSITIVE)
def test_machine_token_denied_on_sensitive_routes(machine_client, method, path, body):
    r = machine_client.request(method, path, headers=H, json=body)
    assert r.status_code == 403, (path, r.status_code, r.text[:120])


@pytest.mark.parametrize("method,path", [
    ("POST", "/api/v1/jobs/recover"), ("POST", "/api/jobs/drain-queued"),
    ("GET", "/api/v1/ready"),
])
def test_machine_token_still_allowed_on_operational_routes(machine_client, method, path):
    r = machine_client.request(method, path, headers=H, json={})
    assert r.status_code not in (401, 403), (path, r.status_code, r.text[:120])


def test_no_token_still_401(machine_client):
    assert machine_client.get("/api/keys").status_code == 401


def test_real_admin_session_still_allowed(db, monkeypatch):
    """A verified owner/admin must keep access to the guarded routes."""
    from types import SimpleNamespace
    from lead_engine.api import app as app_module
    from lead_engine.api import auth_jwt
    monkeypatch.setattr(auth_jwt, "is_admin", lambda claims, d: True)
    req = SimpleNamespace(state=SimpleNamespace(claims={"sub": "u1"}, machine=False),
                          url=SimpleNamespace(path="/api/keys"))
    assert app_module.require_admin(req, db) is None


def test_non_admin_member_still_denied(db, monkeypatch):
    from types import SimpleNamespace
    from fastapi import HTTPException
    from lead_engine.api import app as app_module
    from lead_engine.api import auth_jwt
    monkeypatch.setattr(auth_jwt, "is_admin", lambda claims, d: False)
    req = SimpleNamespace(state=SimpleNamespace(claims={"sub": "u1"}, machine=False),
                          url=SimpleNamespace(path="/api/keys"))
    with pytest.raises(HTTPException) as ei:
        app_module.require_admin(req, db)
    assert ei.value.status_code == 403


# ---- A3: code tools in chat / MCP are admin-only
PRIVILEGED = ["list_code", "read_code", "search_code", "git_history", "git_show",
              "run_tests", "propose_patch"]


def test_privileged_tool_set_is_derived_from_scopes():
    from lead_engine.api.chat import PRIVILEGED_TOOLS, TOOL_SCOPES
    assert set(PRIVILEGED) <= set(PRIVILEGED_TOOLS)
    # nothing privileged may be added to TOOL_SCOPES without being gated
    for name, scopes in TOOL_SCOPES.items():
        if any(s.startswith("code:") or s == "tests:run" for s in scopes):
            assert name in PRIVILEGED_TOOLS


@pytest.mark.parametrize("tool", PRIVILEGED)
def test_execute_tool_refuses_code_tools_by_default(db, tool):
    from lead_engine.api.chat import execute_tool
    out = execute_tool(tool, {"path": "README.md", "query": "x", "patch": "", "title": "t"}, None, db)
    assert "error" in out and "admin" in out["error"].lower()


def test_execute_tool_runs_code_tool_for_admin(db):
    from lead_engine.api.chat import execute_tool
    out = execute_tool("list_code", {}, None, db, privileged=True)
    assert "admin" not in str(out.get("error", "")).lower()


def test_non_privileged_tools_unaffected(db):
    from lead_engine.api.chat import execute_tool
    out = execute_tool("system_status", {}, None, db)
    assert "admin" not in str(out.get("error", "")).lower()


def test_mcp_code_tool_denied_for_non_admin(db):
    from lead_engine.api.mcp import handle_jsonrpc
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "read_code", "arguments": {"path": "lead_engine/db.py"}}}
    payload, _ = handle_jsonrpc(body, None, db)
    assert payload["result"]["isError"] is True
    assert "def open_db" not in payload["result"]["content"][0]["text"]


def test_mcp_tools_list_hides_code_tools_for_non_admin(db):
    from lead_engine.api.mcp import handle_jsonrpc
    payload, _ = handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, None, db)
    names = {t["name"] for t in payload["result"]["tools"]}
    assert not (names & set(PRIVILEGED))
    payload, _ = handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, None, db, privileged=True)
    assert set(PRIVILEGED) <= {t["name"] for t in payload["result"]["tools"]}


def test_sensitive_route_tests_never_touch_the_repo(machine_client):
    """Guard for the sandbox itself: hammer every write route, repo stays clean."""
    import subprocess
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    before = subprocess.run(["git", "status", "--porcelain", "--", "config", ".env"],
                            cwd=root, capture_output=True, text=True).stdout
    for method, path, body in SENSITIVE:
        machine_client.request(method, path, headers=H, json=body)
    after = subprocess.run(["git", "status", "--porcelain", "--", "config", ".env"],
                           cwd=root, capture_output=True, text=True).stdout
    assert before == after


def test_mcp_endpoint_http_hides_and_blocks_code_tools_for_machine_token(machine_client):
    r = machine_client.post("/mcp", headers=H, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = {t["name"] for t in r.json()["result"]["tools"]}
    assert "read_code" not in names and "run_lead_generation" in names
    r = machine_client.post("/mcp", headers=H, json={
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "read_code", "arguments": {"path": "lead_engine/db.py"}}})
    res = r.json()["result"]
    assert res["isError"] is True and "def open_db" not in res["content"][0]["text"]


def test_chat_endpoint_never_declares_code_tools_to_non_admin(machine_client, monkeypatch):
    seen = {}

    class FakeRouter:
        def __init__(self, *a, **k): pass
        def route(self, task, payload, **k):
            seen["tools"] = payload.get("tools")
            return {"text": "ok", "function_calls": []}, {"provider": "fake"}
    monkeypatch.setattr("lead_engine.api.app.Router", FakeRouter)
    machine_client.post("/api/chat", headers=H, json={
        "messages": [{"role": "user", "content": "hi"}],
        "tools": ["read_code", "run_tests", "list_leads"]})
    declared = {d["name"] for t in (seen.get("tools") or []) for d in t["function_declarations"]}
    assert declared == {"list_leads"}
