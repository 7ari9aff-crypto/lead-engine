"""Multi-key pool rotation: 5 Tavily keys = 5x credits, rotate before failover."""
import pytest

from lead_engine.cache import CacheLayer
from lead_engine.config import load_cache_policy
from lead_engine.db import Database
from lead_engine.router import RateLimited, Router


class PooledAdapter:
    tasks = ("web_search",)
    available = True

    def __init__(self, name, key_count, fail_times):
        self.name = name
        self._keys = [f"key{i}" for i in range(key_count)]
        self._key_index = 0
        self.fail_times = fail_times   # first N calls raise RateLimited
        self.calls = 0
        self.keys_used = []

    @property
    def keys(self):
        return self._keys

    def current_key(self):
        return self._keys[min(self._key_index, len(self._keys) - 1)]

    def rotate_key(self):
        if self._key_index < len(self._keys) - 1:
            self._key_index += 1
            return True
        return False

    def request(self, task, payload):
        self.calls += 1
        self.keys_used.append(self.current_key())
        if self.calls <= self.fail_times:
            raise RateLimited("429", retry_after=60)
        return {"provider": self.name, "results": [{"title": "ok"}], "units": 1}


@pytest.fixture()
def router(tmp_path, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "key0,key1,key2,key3,key4")
    db = Database(tmp_path / "r.sqlite3")
    return Router(db, CacheLayer(db, load_cache_policy()), {})


def test_rotates_keys_before_switching_provider(router):
    adapter = PooledAdapter("tavily", 3, fail_times=2)  # key0, key1 fail -> key2 works
    router.adapters = {"tavily": adapter}
    result, meta = router.route("web_search", {"query": "q"}, use_cache=False)
    assert meta["provider"] == "tavily"          # stayed on the same provider
    assert adapter.calls == 3
    assert adapter.keys_used == ["key0", "key1", "key2"]


def test_exhausted_pool_marks_provider_exhausted(router, monkeypatch):
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "bk")
    adapter = PooledAdapter("tavily", 2, fail_times=5)  # every key fails
    router.adapters = {"tavily": adapter, "brave": PooledAdapter("brave", 1, 0)}
    result, meta = router.route("web_search", {"query": "q"}, use_cache=False)
    assert meta["provider"] == "brave"           # pool ran out -> switched provider
    rows = {r["name"]: r for r in router.registry.providers_for_task("web_search")}
    assert rows["tavily"]["status"] == "cooldown"


def test_effective_quota_multiplies_by_pool_size(router):
    counts = {"tavily": 5}
    rows = router.registry.providers_for_task("web_search", key_counts=counts)
    tavily = next(r for r in rows if r["name"] == "tavily")
    assert tavily["quota_limit"] == 1000
    assert tavily["quota_limit_effective"] == 5000
