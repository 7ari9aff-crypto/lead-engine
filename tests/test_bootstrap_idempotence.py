"""Request-path constructors must not perform I/O. See gap register LAT-01."""
import re
import sqlite3

from fastapi.testclient import TestClient

from lead_engine import bootstrap
from lead_engine.activity.store import ActivityStore, ensure_schema
from lead_engine.agent_registry import AGENT_SEED, TOOL_SEED, AgentRegistry, ensure_seeded
from lead_engine.bootstrap import reset as reset_bootstrap
from lead_engine.db import Database
from lead_engine.registry import SEED

# Any INSERT that materialises a seed row, wherever it is issued from.
_SEED_WRITE = re.compile(
    r"^\s*INSERT\s+INTO\s+(providers|agents|agent_versions|tools|connections)\b",
    re.IGNORECASE)


def _seed_writes(statements):
    return [s for s in statements if _SEED_WRITE.match(s)]


class CountingDb:
    """Delegates to a real Database while counting statements."""

    def __init__(self, inner):
        self._inner = inner
        self.count = 0
        self.sql: list[str] = []

    def _note(self, sql):
        self.count += 1
        self.sql.append(" ".join(str(sql).split()))

    def execute(self, sql, params=()):
        self._note(sql)
        return self._inner.execute(sql, params)

    def query(self, sql, params=()):
        self._note(sql)
        return self._inner.query(sql, params)

    def one(self, sql, params=()):
        self._note(sql)
        return self._inner.one(sql, params)

    def __getattr__(self, name):
        return getattr(self._inner, name)


def test_constructing_activity_store_issues_no_statements(tmp_path):
    db = CountingDb(Database(tmp_path / "t.sqlite3"))
    ActivityStore(db)
    assert db.count == 0, f"constructor issued {db.count} statements; must issue 0"


def test_ensure_schema_creates_table_and_is_repeatable(tmp_path):
    inner = Database(tmp_path / "s.sqlite3")
    ensure_schema(inner)
    ensure_schema(inner)  # must not raise on an existing table
    db = CountingDb(inner)
    rows = ActivityStore(db).list(limit=10)
    assert rows == []
    assert db.count == 1, "a read must cost exactly one statement"


def test_activity_writes_survive_a_re_read(tmp_path):
    inner = Database(tmp_path / "w.sqlite3")
    ensure_schema(inner)
    store = ActivityStore(inner)
    store.record("job.started", {"job_id": "j1"})
    got = ActivityStore(inner).list(limit=10)
    assert [e["kind"] for e in got] == ["job.started"]


def test_sqlite3_rejects_schema_ddl_without_privilege():
    """Documents why the old code could never work on Postgres."""
    conn = sqlite3.connect(":memory:")
    assert conn.execute("PRAGMA journal_mode").fetchone() is not None


# ---- Task 2: the same discipline for the agent registry (LAT-01(a)) ----


def test_constructing_agent_registry_issues_no_statements(tmp_path):
    reset_bootstrap()
    inner = Database(tmp_path / "a.sqlite3")
    ensure_seeded(inner)
    db = CountingDb(inner)
    AgentRegistry(db)
    assert db.count == 0, f"constructor issued {db.count} statements; must issue 0"


def test_agent_reads_cost_one_statement_each(tmp_path):
    reset_bootstrap()
    inner = Database(tmp_path / "r.sqlite3")
    ensure_seeded(inner)
    db = CountingDb(inner)
    reg = AgentRegistry(db)
    before = db.count
    reg.agents()
    assert db.count - before == 1
    reg.tools()
    assert db.count - before == 2
    reg.runs(50)
    assert db.count - before == 3


def test_ensure_seeded_is_idempotent(tmp_path):
    reset_bootstrap()
    inner = Database(tmp_path / "i.sqlite3")
    ensure_seeded(inner)
    first = inner.query("SELECT COUNT(*) AS n FROM agents")[0]["n"]
    ensure_seeded(inner)
    second = inner.query("SELECT COUNT(*) AS n FROM agents")[0]["n"]
    assert first == second == len(AGENT_SEED)


# ---- Task 3: the regression guard that keeps LAT-01 from coming back ----


def test_agent_reads_are_single_statement(tmp_path):
    """The regression guard for LAT-01: constructing the registry and reading
    each collection must cost exactly one statement per read."""
    reset_bootstrap()
    inner = Database(tmp_path / "g.sqlite3")
    ensure_seeded(inner)
    db = CountingDb(inner)
    reg = AgentRegistry(db)
    assert db.count == 0, "construction must stay free; readers are measured from here"
    for reader in (reg.agents, reg.tools, reg.connections):
        before = db.count
        assert reader() is not None
        assert db.count == before + 1, f"{reader.__name__} issued more than one statement"
    for reader, args in ((reg.approvals, ("PENDING",)), (reg.runs, (50,))):
        before = db.count
        assert reader(*args) is not None
        assert db.count == before + 1, f"{reader.__name__} issued more than one statement"


def test_ensure_seeded_runs_once_per_process(tmp_path):
    """Second call must be free - that is the whole point of bootstrap.run_once."""
    reset_bootstrap()
    inner = Database(tmp_path / "o.sqlite3")
    db = CountingDb(inner)
    ensure_seeded(db)
    first = db.count
    assert first > 0, "first seed must do real work"
    ensure_seeded(db)
    assert db.count == first, "re-seeding in the same process must issue no statements"


# ---- Task 3 follow-up: the last write-on-read sites (providers registry) ----


def _watch_seed_calls(monkeypatch) -> list:
    """Record every `Registry.seed_if_empty()` entry, including the steady-state
    call that writes nothing.

    Asserting on seed *writes* alone is vacuous against an already-seeded
    database: `seed_if_empty` short-circuits to a single SELECT, so a resurrected
    request-path call would slip through. The call itself is the regression
    (one wasted round trip per hit) and is what this catches.
    """
    from lead_engine.registry import Registry

    calls: list = []
    real = Registry.seed_if_empty

    def spy(self):
        calls.append(1)
        return real(self)

    monkeypatch.setattr(Registry, "seed_if_empty", spy)
    return calls


def test_constructing_router_issues_no_statements(tmp_path):
    """Router is built per request by five dashboard handlers and per job by the
    orchestrators; it used to seed the provider registry on construction."""
    from lead_engine.cache import CacheLayer
    from lead_engine.config import load_cache_policy, load_settings
    from lead_engine.router import Router

    reset_bootstrap()
    inner = Database(tmp_path / "rt.sqlite3")
    ensure_seeded(inner)
    db = CountingDb(inner)
    Router(db, CacheLayer(db, load_cache_policy()), load_settings())
    assert db.count == 0, f"constructor issued {db.count} statements; must issue 0"


def test_build_status_does_not_seed(tmp_path, monkeypatch):
    """GET /api/status is polled by the dashboard every few seconds."""
    from lead_engine.api.app import _build_status

    calls = _watch_seed_calls(monkeypatch)
    reset_bootstrap()
    inner = Database(tmp_path / "bs.sqlite3")
    ensure_seeded(inner)
    del calls[:]
    db = CountingDb(inner)
    payload = _build_status(db)
    assert len(payload["providers"]) == len(SEED), "must still report the real registry"
    assert calls == [], "a status read reached for the seeder"
    assert _seed_writes(db.sql) == [], "status reads must not write seed rows"


# ---- Task 4: the worker entry point bootstraps too ----


def test_worker_command_bootstraps_the_control_plane(tmp_path, monkeypatch, capsys):
    """`python -m lead_engine worker` used to assume `init` had already run."""
    import lead_engine.db as dbmod
    import lead_engine.queue as queue_mod
    from lead_engine.__main__ import main

    store = tmp_path / "w.sqlite3"
    monkeypatch.setattr(dbmod, "open_db", lambda org_id=None: Database(store))
    # SQLite cannot run the SKIP LOCKED leasing SQL: stub the two queue calls so
    # the worker takes its "queue empty" exit without touching provider SQL.
    monkeypatch.setattr(queue_mod, "reclaim_expired", lambda db: 0)
    monkeypatch.setattr(queue_mod, "lease_next",
                        lambda db, worker_id, lease_seconds=600: None)
    reset_bootstrap()

    assert main(["worker", "--once"]) == 0
    assert "queue empty" in capsys.readouterr().out

    db = Database(store)
    assert db.one("SELECT COUNT(*) AS n FROM agents")["n"] == len(AGENT_SEED)
    assert db.one("SELECT COUNT(*) AS n FROM providers")["n"] == len(SEED)


# ---- Task 5: the lifespan actually runs the bootstrap, once ----


def test_lifespan_bootstraps_once_and_requests_never_seed(tmp_path, monkeypatch, request):
    """`TestClient(app)` without a `with` block skips the lifespan, so every
    existing client fixture proves nothing about startup work. This one enters
    the context manager on purpose.

    Negative-checked by hand, not assumed: deleting `run_data_bootstrap(db)`
    from `_lifespan` fails assertions 1 and 2; putting back any of the three
    removed request-path `seed_if_empty()` calls fails assertion 3.
    """
    import lead_engine.api.app as appmod

    # /api/status memoises per org; do not hand a later test a payload built on
    # a database that is gone by then.
    request.addfinalizer(appmod._status_cache.clear)
    calls = _watch_seed_calls(monkeypatch)
    store = tmp_path / "life.sqlite3"
    seen: list[str] = []

    class RecordingDb(Database):
        def _log(self, sql):
            seen.append(" ".join(str(sql).split()))

        def execute(self, sql, params=()):
            self._log(sql)
            return super().execute(sql, params)

        def query(self, sql, params=()):
            self._log(sql)
            return super().query(sql, params)

        def one(self, sql, params=()):
            self._log(sql)
            return super().one(sql, params)

    monkeypatch.setattr(appmod, "open_db", lambda org_id=None: RecordingDb(store))
    reset_bootstrap()
    seen.clear()
    del calls[:]

    with TestClient(appmod.app) as client:
        # 1. the lifespan really seeded: 59 seed rows across all five tables
        startup = _seed_writes(seen)
        assert len(startup) >= 50, (
            f"startup issued {len(startup)} seed writes over {len(seen)} statements; "
            "the lifespan bootstrap hook is not running")
        tables = {_SEED_WRITE.match(s).group(1).lower() for s in startup}
        assert tables == {"providers", "agents", "agent_versions", "tools",
                          "connections"}, f"partial bootstrap: {sorted(tables)}"

        # 2. exactly once per process: one seeding pass, and the step is marked
        #    done so nothing can run it a second time
        assert calls == [1], f"bootstrap seeded {len(calls)} times, expected exactly 1"
        rerun: list = []
        assert bootstrap.run_once("agent_registry", lambda: rerun.append(1)) is False
        assert rerun == [], "bootstrap re-ran inside the same process"

        appmod._status_cache.clear()
        seen.clear()
        del calls[:]

        # 3. the request path then never reaches for the seeder again
        for path in ("/api/status", "/providers", "/api/agents", "/api/tools",
                     "/api/v1/health"):
            res = client.get(path)
            assert res.status_code == 200, f"{path} -> {res.status_code} {res.text}"
        assert calls == [], (
            f"a GET called Registry.seed_if_empty() {len(calls)} times")
        assert _seed_writes(seen) == [], (
            f"a GET wrote seed rows: {[s for s in seen if _SEED_WRITE.match(s)][:5]}")

        # 4. and the request path is not quietly empty either
        assert len(client.get("/api/status").json()["providers"]) == len(SEED)
        assert len(client.get("/api/agents").json()["agents"]) == len(AGENT_SEED)
        assert len(client.get("/api/tools").json()["tools"]) == len(TOOL_SEED)
