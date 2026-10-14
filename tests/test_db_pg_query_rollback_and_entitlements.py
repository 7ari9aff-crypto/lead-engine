"""Two fixes found by the first REAL agent research run (2026-10-14):

1. `entitlements.check_provider_call` qualified the ENGINE table usage_ledger
   as `public.usage_ledger`. The engine connection pins search_path=engine,
   so every provider call on Postgres died with UndefinedTable — the planner
   model call never happened and the research job could not start.
2. `PgDatabase.query()` did not roll back after a failed statement (execute()
   did). The aborted transaction then poisoned every later statement on the
   pooled connection — including the job's own FAILED transition, which is
   why the job stayed stuck in DISCOVERING instead of failing honestly.
"""
import sys
import types

import pytest

from lead_engine import db_pg
from lead_engine.db_pg import PgDatabase, reset_pools


class FailingCursor:
    def __init__(self):
        self.calls = 0

    def execute(self, *a, **kw):
        self.calls += 1
        raise RuntimeError("relation does not exist")

    def fetchall(self):
        return []


class RollbackTrackingConn:
    def __init__(self):
        self.rolled_back = 0
        self.cursor_calls = 0

    def rollback(self):
        self.rolled_back += 1

    def commit(self):
        pass

    def close(self):
        pass

    def cursor(self):
        self.cursor_calls += 1
        return FailingCursor()


class TrackingPool:
    check_connection = staticmethod(lambda conn: True)

    def __init__(self, conninfo=None, kwargs=None, **kw):
        self.conn = RollbackTrackingConn()

    def getconn(self, timeout=None):
        return self.conn

    def putconn(self, conn):
        pass

    def close(self):
        pass


@pytest.fixture()
def tracking_pool(monkeypatch):
    mod = types.SimpleNamespace(ConnectionPool=TrackingPool)
    monkeypatch.setitem(sys.modules, "psycopg_pool", mod)
    monkeypatch.setattr(db_pg, "_audit_db_role", lambda dsn: None)
    reset_pools()
    yield TrackingPool
    reset_pools()


def test_query_rolls_back_after_failed_statement(tracking_pool, monkeypatch):
    # org unset so _bind_org issues no GUC statement before the failing one
    db = PgDatabase(DSN, org_id=None)
    with pytest.raises(RuntimeError):
        db.query("SELECT * FROM missing_table")
    # the rollback is what keeps the connection usable for the caller's own
    # error handling — without it every later statement raises
    # InFailedSqlTransaction (the stuck-in-DISCOVERING failure mode)
    assert db.conn._conn.rolled_back >= 1


def test_query_still_commits_on_success(tracking_pool, monkeypatch):
    # same harness, but the cursor succeeds: no rollback must fire
    class OkCursor:
        def execute(self, *a, **kw):
            pass

        def fetchall(self):
            return [{"n": 1}]

    class OkConn(RollbackTrackingConn):
        def cursor(self):
            return OkCursor()

    monkeypatch.setattr(TrackingPool, "getconn", lambda self, timeout=None: OkConn())
    db = PgDatabase(DSN, org_id=None)
    rows = db.query("SELECT 1 AS n")
    assert rows == [{"n": 1}]
    assert db.conn._conn.rolled_back == 0


DSN = "postgresql://u:p@db.example.test:5432/db"


# ---------------------------------------------------------------- entitlements
class RecordingDb:
    """Minimal db.one harness that records SQL and answers by table."""

    dialect = "postgres"

    def __init__(self, answers):
        self.sqls = []
        self.answers = answers

    def one(self, sql, params=()):
        self.sqls.append(sql)
        for needle, row in self.answers.items():
            if needle in sql:
                return row
        return None


def test_provider_call_budget_reads_engine_usage_ledger_unqualified():
    from lead_engine.entitlements import check_provider_call

    db = RecordingDb({
        "organizations": {"limits": None},
        "usage_ledger": {"n": 0},
    })
    assert check_provider_call(db, "org-1") is True
    ledger_sql = [s for s in db.sqls if "usage_ledger" in s][0]
    assert "public.usage_ledger" not in ledger_sql
    assert "FROM usage_ledger" in ledger_sql


def test_provider_call_budget_blocks_when_over_limit():
    from lead_engine.entitlements import check_provider_call

    db = RecordingDb({
        "organizations": {"limits": '{"max_provider_calls_per_day": 2}'},
        "usage_ledger": {"n": 2},
    })
    assert check_provider_call(db, "org-1") is False


def test_job_start_budget_reads_engine_jobs_unqualified():
    from lead_engine.entitlements import check_job_start

    db = RecordingDb({
        "organizations": {"limits": None},
        "jobs": {"n": 0},
    })
    allowed, reason = check_job_start(db, "org-1")
    assert allowed is True
    jobs_sql = [s for s in db.sqls if "FROM jobs" in s][0]
    assert "public.jobs" not in jobs_sql
