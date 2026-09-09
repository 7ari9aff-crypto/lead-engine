import pytest

from lead_engine.cache import CacheLayer
from lead_engine.config import load_cache_policy
from lead_engine.db import Database
from lead_engine.router import (
    NoProviderAvailable, ProviderUnavailable, QuotaExhausted, RateLimited, Router,
)


class FakeAdapter:
    tasks = ("web_search",)
    available = True
    keys: list = []

    def __init__(self, name, behavior):
        self.name = name
        self.behavior = behavior

    def current_key(self):
        return self.keys[0] if self.keys else None

    def rotate_key(self):
        return False

    def request(self, task, payload):
        action = self.behavior
        if action == "rate_limited":
            raise RateLimited("429", retry_after=60)
        if action == "quota":
            raise QuotaExhausted("credits over")
        if action == "unavailable":
            raise ProviderUnavailable("connection failed")
        return {"provider": self.name, "results": [{"title": f"from {self.name}"}], "units": 1}


@pytest.fixture()
def router(tmp_path, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "test-key")
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    db = Database(tmp_path / "r.sqlite3")
    return Router(db, CacheLayer(db, load_cache_policy()), {})


def test_failover_on_rate_limit(router):
    router.adapters = {"tavily": FakeAdapter("tavily", "rate_limited"),
                       "brave": FakeAdapter("brave", "ok")}
    result, meta = router.route("web_search", {"query": "q1"}, use_cache=False)
    assert meta["provider"] == "brave"
    rows = {r["name"]: r for r in router.registry.providers_for_task("web_search")}
    assert rows["tavily"]["status"] == "cooldown"
    assert rows["brave"]["status"] == "active"


def test_failover_to_exhausted_then_no_provider(router):
    router.adapters = {"tavily": FakeAdapter("tavily", "quota"),
                       "brave": FakeAdapter("brave", "quota"),
                       "exa": FakeAdapter("exa", "quota")}
    with pytest.raises(NoProviderAvailable):
        router.route("web_search", {"query": "q2"}, use_cache=False)
    rows = {r["name"]: r for r in router.registry.providers_for_task("web_search")}
    assert all(r["status"] == "exhausted" for r in rows.values())


def test_usage_ledger_records_calls(router):
    router.adapters = {"tavily": FakeAdapter("tavily", "ok")}
    router.route("web_search", {"query": "q3"}, use_cache=False)
    usage = router.usage_report()
    assert usage[0]["provider"] == "tavily"
    assert usage[0]["calls"] == 1


def test_cache_hit_skips_providers(router):
    router.adapters = {"tavily": FakeAdapter("tavily", "ok")}
    router.route("web_search", {"query": "same"})
    result, meta = router.route("web_search", {"query": "same"})
    assert meta["cached"] is True
    assert meta["provider"] == "cache"


def test_proactive_rate_headers_cooldown(router):
    router.adapters = {"tavily": FakeAdapter("tavily", "ok")}
    result, _ = router.route("web_search", {"query": "q4"}, use_cache=False)
    assert result["results"]
    # provider header says 0 remaining -> registry cools it down
    router.registry.set_rpm_from_headers("tavily", "web_search", 0)
    rows = {r["name"]: r for r in router.registry.providers_for_task("web_search")}
    assert rows["tavily"]["status"] == "cooldown"
