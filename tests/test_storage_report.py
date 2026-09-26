"""The app must be able to say which store it is actually on.

Why: production E2E (2026-09-26) showed the API answering while job execution failed
with `OperationalError: database is locked` — a SQLite error — and no endpoint could
distinguish "Postgres with a real tenant database" from "SQLite fallback on an
ephemeral serverless filesystem". Every diagnosis was guesswork until the app itself
admitted its backend, so this makes it say so on the surface the dashboard already
polls, with zero extra queries (the statement budget in
tests/test_status_statement_budget.py still applies).

Credentials never leave: only the host is reported, and the test pins that with a
DSN that carries a password.
"""
from lead_engine.api.app import _storage_report


class PgDatabase:
    """Stands in for lead_engine.db_pg.PgDatabase without opening a connection.
    Named exactly like the real class because the backend is discriminated by
    class name, not by import (importing db_pg pulls in psycopg)."""

    __slots__ = ()


def test_sqlite_when_no_dsn(monkeypatch):
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from lead_engine.db import Database
    report = _storage_report(Database(":memory:"))
    assert report["backend"] == "sqlite"
    assert report["dsn_present"] is False
    assert report["dsn_host"] is None


def test_postgres_reported_with_dsn_and_masked_host():
    from lead_engine.db import Database
    db = Database(":memory:")
    dsn = "postgresql://postgres.abc123:sup3r-s3cret@aws-1-eu-west-1.pooler.supabase.com:6543/postgres"
    report = _storage_report(PgDatabase(), dsn=dsn)
    assert report["backend"] == "postgres"
    assert report["dsn_present"] is True
    assert report["dsn_host"] == "aws-1-eu-west-1.pooler.supabase.com:6543"
    # the whole point of the masking
    assert "sup3r-s3cret" not in str(report)
    assert "postgres.abc123" not in str(report)


def test_status_endpoint_carries_storage():
    import json

    import fastapi
    from fastapi.testclient import TestClient

    from lead_engine.api import app as appmod

    client = TestClient(appmod.app)
    r = client.get("/api/status")
    assert r.status_code == 200
    storage = r.json()["storage"]
    assert storage["backend"] in {"sqlite", "postgres"}
    assert isinstance(storage["dsn_present"], bool)
    assert "sup3r" not in json.dumps(r.json())
