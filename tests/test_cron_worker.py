"""The Vercel cron worker endpoint (api/cron/worker.py).

Drives the handler as a raw ASGI app — no framework, no network. The tick
itself is faked at its import point; its behaviour is covered by
tests/test_worker_tick.py.
"""
import asyncio
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

from lead_engine.db import Database

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "api" / "cron" / "worker.py"

SECRET = "cron-secret-1"


def load_handler():
    spec = importlib.util.spec_from_file_location("cron_worker_under_test", MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod.handler


async def drive(app, headers):
    scope = {"type": "http", "method": "GET", "path": "/api/cron/worker",
             "headers": headers, "query_string": b"", "http_version": "1.1"}
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        sent.append(msg)

    await app(scope, receive, send)
    status = sent[0]["status"]
    body = b"".join(m.get("body", b"") for m in sent[1:])
    return status, body


def bearer(token):
    return [(b"authorization", f"Bearer {token}".encode())]


def test_missing_configuration_rejects(monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "")
    status, _ = asyncio.run(drive(load_handler(), []))
    assert status == 401


def test_wrong_token_rejects(monkeypatch):
    monkeypatch.setenv("CRON_SECRET", SECRET)
    status, _ = asyncio.run(drive(load_handler(), bearer("nope")))
    assert status == 401


def test_valid_cron_runs_one_tick(monkeypatch, tmp_path):
    monkeypatch.setenv("CRON_SECRET", SECRET)
    opened = []
    tick_args = {}

    def fake_open_db():
        db = Database(tmp_path / "cron.sqlite3")
        opened.append(db)
        return db

    def fake_tick(db, worker_id, settings=None, lease_seconds=600):
        tick_args["worker_id"] = worker_id
        tick_args["db"] = db
        return {"worker_id": worker_id, "reclaimed": 1, "leased": False,
                "job_id": None, "state": None, "error": None}

    monkeypatch.setattr("lead_engine.db.open_db", fake_open_db)
    monkeypatch.setattr("lead_engine.worker.run_worker_tick", fake_tick)

    status, body = asyncio.run(drive(load_handler(), bearer(SECRET)))

    assert status == 200
    assert json.loads(body)["reclaimed"] == 1
    assert tick_args["worker_id"].startswith("cron-")
    assert opened and tick_args["db"] is opened[0]
    with pytest.raises(sqlite3.ProgrammingError):
        opened[0].conn.execute("select 1")  # db was closed by the handler


def test_tick_failure_returns_500_not_crash(monkeypatch, tmp_path):
    monkeypatch.setenv("CRON_SECRET", SECRET)

    def fake_open_db():
        return Database(tmp_path / "cron2.sqlite3")

    def fake_tick(db, worker_id, settings=None, lease_seconds=600):
        raise RuntimeError("db down")

    monkeypatch.setattr("lead_engine.db.open_db", fake_open_db)
    monkeypatch.setattr("lead_engine.worker.run_worker_tick", fake_tick)

    status, body = asyncio.run(drive(load_handler(), bearer(SECRET)))

    assert status == 500
    assert "db down" in json.loads(body)["error"]
