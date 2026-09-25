"""Unit tests for connection pooling in db_pg.py — no database required.

CI has no Postgres, so these tests replace psycopg_pool with fakes (or hide
it entirely) and verify the pool lifecycle decisions and the connection
return path, which is where a leak would hide.
"""
import sys
import types

import pytest

from lead_engine import db_pg
from lead_engine.db_pg import (
    _POOL_DISABLED,
    PgDatabase,
    _ConnProxy,
    _get_pool,
    reset_pools,
)

DSN = "postgresql://u:p@db.example.test:5432/db"
OTHER_DSN = "postgresql://u:p@other.example.test:5432/db"


class FakeConn:
    def __init__(self):
        self.rolled_back = 0
        self.closed = False
        self.cursor_calls = 0

    def rollback(self):
        self.rolled_back += 1

    def close(self):
        self.closed = True

    def cursor(self):
        self.cursor_calls += 1
        raise AssertionError("not expected in these tests")


class FakePool:
    check_connection = staticmethod(lambda conn: True)

    def __init__(self, conninfo=None, kwargs=None, **kw):
        self.conninfo = conninfo
        self.kwargs = kwargs
        self.kw = kw
        self.getconn_calls = 0
        self.putconn_calls = []
        self.closed = False
        FakePool.instances.append(self)

    def getconn(self, timeout=None):
        self.getconn_calls += 1
        return FakeConn()

    def putconn(self, conn):
        self.putconn_calls.append(conn)

    def close(self):
        self.closed = True


FakePool.instances = []


@pytest.fixture()
def fake_pool_module(monkeypatch):
    """Install FakePool as psycopg_pool and stub the role probe (which would
    otherwise attempt a real connection). Restores everything afterwards."""
    mod = types.SimpleNamespace(ConnectionPool=FakePool)
    monkeypatch.setitem(sys.modules, "psycopg_pool", mod)
    monkeypatch.setattr(db_pg, "_audit_db_role", lambda dsn: None)
    reset_pools()
    FakePool.instances = []
    yield mod
    reset_pools()


def _patch_connect(monkeypatch):
    conns = []

    def fake_connect(dsn, **kwargs):
        conns.append((dsn, kwargs))
        return FakeConn()

    monkeypatch.setattr(db_pg.psycopg, "connect", fake_connect)
    return conns


def test_pool_disabled_by_env(monkeypatch, fake_pool_module):
    monkeypatch.setenv("LEAD_ENGINE_DB_POOL", "0")
    assert _get_pool(DSN, {}) is None
    assert FakePool.instances == []
    # the disabled decision is not cached, so re-enabling works immediately
    monkeypatch.delenv("LEAD_ENGINE_DB_POOL")
    assert isinstance(_get_pool(DSN, {}), FakePool)


def test_get_pool_reused_per_dsn(fake_pool_module):
    pool_a1 = _get_pool(DSN, {"autocommit": False})
    pool_a2 = _get_pool(DSN, {"autocommit": False})
    pool_b = _get_pool(OTHER_DSN, {})
    assert pool_a1 is pool_a2
    assert pool_b is not pool_a1
    assert len(FakePool.instances) == 2


def test_pool_kwargs_carry_adapter_requirements(fake_pool_module, monkeypatch):
    monkeypatch.setenv("LEAD_ENGINE_DB_POOL_MAX", "3")
    kwargs = {
        "row_factory": "sentinel-row-factory",
        "autocommit": False,
        "options": "-c search_path=engine",
        "prepare_threshold": None,
    }
    pool = _get_pool(DSN, kwargs)
    assert pool.kwargs == kwargs
    assert pool.kw["min_size"] == 1
    assert pool.kw["max_size"] == 3
    assert callable(pool.kw["check"])


def test_close_returns_connection_to_pool(fake_pool_module):
    db = PgDatabase(DSN, org_id="org-1")
    pool = _get_pool(DSN, {})
    raw = db.conn._conn
    assert pool.getconn_calls == 1

    db.close()
    assert pool.putconn_calls == [raw]
    assert raw.rolled_back == 1
    assert raw.closed is False
    with pytest.raises(AttributeError):
        db.conn.cursor()
    # double close is a no-op
    db.close()
    assert pool.putconn_calls == [raw]


def test_direct_conn_close_also_returns_to_pool(fake_pool_module):
    # call sites across the codebase close the raw connection directly
    # (db.conn.close()); with a pool that must not leak the leased slot.
    db = PgDatabase(DSN, org_id="org-1")
    pool = _get_pool(DSN, {})
    raw = db.conn._conn
    db.conn.close()
    assert pool.putconn_calls == [raw]
    assert raw.rolled_back == 1


def test_no_pool_falls_back_to_real_close(monkeypatch, fake_pool_module):
    conns = _patch_connect(monkeypatch)
    monkeypatch.setenv("LEAD_ENGINE_DB_POOL", "0")
    db = PgDatabase(DSN, org_id="org-1")
    raw = db.conn._conn
    assert conns and conns[0][0] == DSN
    db.close()
    assert raw.closed is True
    assert raw.rolled_back == 1


def test_missing_psycopg_pool_module_falls_back(monkeypatch):
    # sys.modules["psycopg_pool"] = None makes `import psycopg_pool` raise
    # ImportError — the no-extra deployment path.
    monkeypatch.setitem(sys.modules, "psycopg_pool", None)
    reset_pools()
    conns = _patch_connect(monkeypatch)
    try:
        assert _get_pool(DSN, {}) is None
        # the fallback decision is cached so later calls skip the import
        assert db_pg._POOLS[DSN] is _POOL_DISABLED
        db = PgDatabase(DSN, org_id=None)
        raw = db.conn._conn
        db.close()
        assert conns[0][0] == DSN
        assert raw.closed is True
    finally:
        reset_pools()


def test_reset_pools_closes_and_forgets(fake_pool_module):
    pool_a = _get_pool(DSN, {})
    pool_b = _get_pool(OTHER_DSN, {})
    reset_pools()
    assert pool_a.closed and pool_b.closed
    assert db_pg._POOLS == {}


def test_proxy_forwards_attribute_access():
    raw = FakeConn()
    proxy = _ConnProxy(raw, lambda conn: None)
    assert proxy.rolled_back == 0
    assert proxy.cursor_calls == 0
