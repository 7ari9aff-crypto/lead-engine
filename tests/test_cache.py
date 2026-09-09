import time

from lead_engine.cache import CacheLayer
from lead_engine.config import load_cache_policy
from lead_engine.db import Database


def test_l1_roundtrip(tmp_path):
    db = Database(tmp_path / "c.sqlite3")
    cache = CacheLayer(db, load_cache_policy())
    payload = {"query": "dental clinic in Jeddah"}
    assert cache.get_request("web_search", payload) is None
    cache.put_request("web_search", payload, {"results": [1, 2, 3]})
    assert cache.get_request("web_search", payload) == {"results": [1, 2, 3]}


def test_l1_different_payload_no_collision(tmp_path):
    db = Database(tmp_path / "c.sqlite3")
    cache = CacheLayer(db, load_cache_policy())
    cache.put_request("web_search", {"query": "a"}, {"r": 1})
    cache.put_request("web_search", {"query": "b"}, {"r": 2})
    assert cache.get_request("web_search", {"query": "a"}) == {"r": 1}
    assert cache.get_request("web_search", {"query": "b"}) == {"r": 2}


def test_l1_expiry(tmp_path):
    db = Database(tmp_path / "c.sqlite3")
    policy = load_cache_policy()
    policy["ttl_days"] = dict(policy["ttl_days"], search_results=0)  # TTL = 0 seconds
    cache = CacheLayer(db, policy)
    cache.put_request("web_search", {"query": "x"}, {"r": 1})
    time.sleep(1.1)
    assert cache.get_request("web_search", {"query": "x"}) is None


def test_l2_entity_and_purge(tmp_path):
    db = Database(tmp_path / "c.sqlite3")
    policy = load_cache_policy()
    cache = CacheLayer(db, policy)
    cache.put_entity("company", "alzahradental.com", {"branches": 3})
    assert cache.get_entity("company", "alzahradental.com") == {"branches": 3}
    policy0 = load_cache_policy()
    policy0["ttl_days"] = dict(policy0["ttl_days"], email=0)
    stale = CacheLayer(db, policy0)
    stale.put_entity("email", "x@y.com", {"ok": True}, data_type="email")
    time.sleep(1.1)
    assert cache.purge_expired() >= 1
