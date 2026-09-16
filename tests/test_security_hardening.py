"""Regression tests pinning the tenant-isolation and auth hardening fixes.

Without these, a future refactor could silently reopen the cross-tenant
leaks (chat tools reading every org's leads) or the placeholder-password
hole (committed dev defaults opening the control plane)."""
import pytest

from lead_engine.api import auth as auth_mod
from lead_engine.cache import CacheLayer
from lead_engine.config import load_cache_policy
from lead_engine.db import Database
from lead_engine.jobs import IllegalTransition, JobManager
from lead_engine.tenant import org_clause


# ---- placeholder passwords never open the plane -------------------------

def test_placeholder_password_behaves_like_unset(monkeypatch):
    monkeypatch.setenv("LEAD_ENGINE_ADMIN_PASSWORD", "dev-admin-password")
    assert auth_mod.configured_password() == ""
    assert auth_mod.enabled() is False
    assert auth_mod.password_matches("dev-admin-password") is False


def test_real_password_still_works(monkeypatch):
    monkeypatch.setenv("LEAD_ENGINE_ADMIN_PASSWORD", "s3cret-value")
    assert auth_mod.configured_password() == "s3cret-value"
    assert auth_mod.enabled() is True
    assert auth_mod.password_matches("s3cret-value") is True


def test_auth_mode_ignores_placeholder_password(monkeypatch):
    from lead_engine.api import auth_jwt

    monkeypatch.setenv("LEAD_ENGINE_ADMIN_PASSWORD", "dev-admin-password")
    # conftest keeps the suite in dev-open mode with no Supabase backend
    assert auth_jwt.auth_mode() != "password"


# ---- cache results are org-scoped ---------------------------------------

def test_cache_keys_are_org_scoped(tmp_path):
    db = Database(tmp_path / "c.sqlite3")
    cache = CacheLayer(db, load_cache_policy())
    db.org_id = "org-a"
    cache.put_request("web_search", {"query": "x"}, {"r": "a"})
    db.org_id = "org-b"
    # tenant B must never be served tenant A's cached search results
    assert cache.get_request("web_search", {"query": "x"}) is None
    db.org_id = "org-a"
    assert cache.get_request("web_search", {"query": "x"}) == {"r": "a"}


# ---- chat/MCP tools are tenant-scoped -----------------------------------

def test_chat_list_leads_scoped_by_org(tmp_path):
    from lead_engine.api.chat import execute_tool

    db = Database(tmp_path / "l.sqlite3")
    db.insert_lead({"lead_id": "o1:a.com", "name": "A", "domain": "a.com", "score": 5})
    db.execute(
        "INSERT INTO leads (lead_id, organization_id, name, score) VALUES (?,?,?,?)",
        ("o2:b.com", "org-2", "B", 9))

    db.org_id = "shared"
    out = execute_tool("list_leads", {"limit": 50}, router=None, db=db)
    assert {r["name"] for r in out["leads"]} == {"A"}

    db.org_id = "org-2"
    out2 = execute_tool("list_leads", {"limit": 50}, router=None, db=db)
    assert {r["name"] for r in out2["leads"]} == {"B"}


def test_org_clause_without_context_stays_compat(tmp_path):
    # no tenant context: empty predicate (legacy single-org SQLite data)
    db = Database(tmp_path / "o.sqlite3")
    assert org_clause(db) == ("", [])


# ---- job transitions refuse concurrent races ----------------------------

def test_transition_race_guard(tmp_path, monkeypatch):
    db = Database(tmp_path / "j.sqlite3")
    jm = JobManager(db)
    job_id = jm.create_job("v0", {})
    jm.transition(job_id, "RUNNING", "start")
    # a concurrent writer (e.g. the user cancelling) flips the state AFTER
    # our read but BEFORE our write: the WHERE state=? guard must refuse
    monkeypatch.setattr(JobManager, "current", lambda self, job_id: "RUNNING")
    db.execute("UPDATE jobs SET state='CANCELLED' WHERE job_id=?", (job_id,))
    with pytest.raises(IllegalTransition):
        jm.transition(job_id, "PAUSED", "capacity")