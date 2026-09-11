"""Tests for ``lead_engine.observability``.

Covers:

* :class:`StructuredLogger` JSON output, extra-field merging, and
  correlation-id stamping,
* :func:`set_correlation_id` / :func:`get_correlation_id` round-tripping,
* :class:`CorrelationIdMiddleware` header handling via FastAPI ``TestClient``,
* every ``emit_*`` helper attaching ``kind=`` and the current correlation id.
"""

from __future__ import annotations

import io
import json
import logging
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from lead_engine.observability import (
    CorrelationIdMiddleware,
    correlation_id_var,
    emit_agent_run_completed,
    emit_agent_run_started,
    emit_approval_requested,
    emit_approval_resolved,
    emit_job_completed,
    emit_job_paused,
    emit_job_started,
    get_correlation_id,
    get_logger,
    set_correlation_id,
)


# ---------------------------------------------------------------------------
# Fixtures: route every log record the module emits through an in-memory
# stream so we can assert on the JSON payload without touching the real
# stderr.
# ---------------------------------------------------------------------------


@pytest.fixture()
def captured_logs(monkeypatch):
    """Attach a StringIO StreamHandler to the root logger for the test."""
    from lead_engine.observability import logger as logger_mod

    logger_mod.reset_logger_state()

    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(logger_mod.JsonFormatter())
    handler.setLevel(logging.DEBUG)

    root = logging.getLogger()
    # Wipe whatever the module installed on its first call so we observe a
    # single, predictable handler.
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)

    # Force JSON format for the duration of the test.
    monkeypatch.setenv("LOG_FORMAT", "json")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    yield buffer

    root.removeHandler(handler)
    logger_mod.reset_logger_state()


def _parse_lines(buf: io.StringIO) -> list[dict]:
    """Parse every newline-delimited JSON line in *buf* into a dict."""
    raw = buf.getvalue().strip()
    if not raw:
        return []
    out: list[dict] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


# ---------------------------------------------------------------------------
# StructuredLogger
# ---------------------------------------------------------------------------


def test_structured_logger_emits_valid_json(captured_logs):
    log = get_logger("test.basic")
    log.info("hello world")

    records = _parse_lines(captured_logs)
    assert len(records) == 1
    rec = records[0]
    assert rec["level"] == "INFO"
    assert rec["logger"] == "test.basic"
    assert rec["message"] == "hello world"
    assert "timestamp" in rec
    # timestamp is ISO-8601 UTC
    assert rec["timestamp"].endswith("+00:00") or rec["timestamp"].endswith("Z")


def test_structured_logger_extra_fields_appear_in_output(captured_logs):
    log = get_logger("test.extras")
    log.warning(
        "something happened",
        user_id=42,
        route="/leads",
        tags=["alpha", "beta"],
    )

    records = _parse_lines(captured_logs)
    assert len(records) == 1
    rec = records[0]
    assert rec["message"] == "something happened"
    assert rec["user_id"] == 42
    assert rec["route"] == "/leads"
    assert rec["tags"] == ["alpha", "beta"]


def test_structured_logger_stamps_correlation_id_from_context(captured_logs):
    log = get_logger("test.cid")
    token = set_correlation_id("cid-abc-123")
    try:
        log.error("boom")
    finally:
        correlation_id_var.reset(token)

    records = _parse_lines(captured_logs)
    assert records[0]["correlation_id"] == "cid-abc-123"


def test_structured_logger_levels(captured_logs):
    log = get_logger("test.levels")
    log.debug("d")
    log.info("i")
    log.warning("w")
    log.error("e")

    records = _parse_lines(captured_logs)
    levels = [r["level"] for r in records]
    assert levels == ["DEBUG", "INFO", "WARNING", "ERROR"]


# ---------------------------------------------------------------------------
# correlation_id context var
# ---------------------------------------------------------------------------


def test_correlation_id_set_get_roundtrip():
    # Make sure we start from a known state.
    correlation_id_var.set(None)
    assert get_correlation_id() is None

    token = set_correlation_id("roundtrip-1")
    try:
        assert get_correlation_id() == "roundtrip-1"
    finally:
        correlation_id_var.reset(token)
    assert get_correlation_id() is None


def test_correlation_id_reset_restores_previous():
    correlation_id_var.set(None)
    token_outer = set_correlation_id("outer")
    try:
        token_inner = set_correlation_id("inner")
        try:
            assert get_correlation_id() == "inner"
        finally:
            correlation_id_var.reset(token_inner)
        assert get_correlation_id() == "outer"
    finally:
        correlation_id_var.reset(token_outer)
    assert get_correlation_id() is None


# ---------------------------------------------------------------------------
# CorrelationIdMiddleware
# ---------------------------------------------------------------------------


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(CorrelationIdMiddleware)

    @app.get("/ping")
    def ping():
        return {"pong": True, "cid": get_correlation_id()}

    @app.post("/echo")
    def echo(payload: dict):
        return {"received": payload, "cid": get_correlation_id()}

    return app


def test_middleware_generates_correlation_id_when_header_missing():
    client = TestClient(_build_app())
    resp = client.get("/ping")
    assert resp.status_code == 200

    cid = resp.headers.get("X-Correlation-ID")
    assert cid, "response must carry a generated X-Correlation-ID"
    # Echoes back the same id that was active inside the handler.
    assert resp.json()["cid"] == cid
    # A hex uuid4 has exactly 32 hex chars.
    assert len(cid) == 32
    int(cid, 16)  # parses as hex without raising


def test_middleware_echoes_inbound_correlation_id():
    client = TestClient(_build_app())
    resp = client.get(
        "/ping",
        headers={"X-Correlation-ID": "abc-from-client"},
    )
    assert resp.status_code == 200
    assert resp.headers.get("X-Correlation-ID") == "abc-from-client"
    assert resp.json()["cid"] == "abc-from-client"


def test_middleware_handles_post_request():
    client = TestClient(_build_app())
    resp = client.post(
        "/echo",
        json={"hello": "world"},
        headers={"X-Correlation-ID": "post-cid-1"},
    )
    assert resp.status_code == 200
    assert resp.headers.get("X-Correlation-ID") == "post-cid-1"
    assert resp.json()["received"] == {"hello": "world"}


# ---------------------------------------------------------------------------
# emit_* helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def with_cid():
    """Set a known correlation id for the duration of one test."""
    correlation_id_var.set(None)
    token = set_correlation_id("emit-cid-xyz")
    yield "emit-cid-xyz"
    correlation_id_var.reset(token)


def _find(records: list[dict], kind: str) -> dict:
    matches = [r for r in records if r.get("kind") == kind]
    assert matches, f"no record with kind={kind!r} in {records!r}"
    return matches[-1]


def test_emit_job_started(with_cid, captured_logs):
    emit_job_started("job-1", "saudi_dental_v0", lead_count=10)
    rec = _find(_parse_lines(captured_logs), "job.started")
    assert rec["job_id"] == "job-1"
    assert rec["icp"] == "saudi_dental_v0"
    assert rec["lead_count"] == 10
    assert rec["correlation_id"] == "emit-cid-xyz"


def test_emit_job_completed(with_cid, captured_logs):
    emit_job_completed(
        "job-2",
        "COMPLETED",
        metrics={"leads": 7, "duration_s": 12.3},
        finished_by="router",
    )
    rec = _find(_parse_lines(captured_logs), "job.completed")
    assert rec["job_id"] == "job-2"
    assert rec["state"] == "COMPLETED"
    assert rec["metrics"] == {"leads": 7, "duration_s": 12.3}
    assert rec["finished_by"] == "router"
    assert rec["correlation_id"] == "emit-cid-xyz"


def test_emit_job_paused(with_cid, captured_logs):
    emit_job_paused("job-3", "no_provider_available")
    rec = _find(_parse_lines(captured_logs), "job.paused")
    assert rec["job_id"] == "job-3"
    assert rec["reason"] == "no_provider_available"
    assert rec["correlation_id"] == "emit-cid-xyz"


def test_emit_agent_run_started(with_cid, captured_logs):
    emit_agent_run_started("run-1", "sa-discovery", attempt=2)
    rec = _find(_parse_lines(captured_logs), "agent_run.started")
    assert rec["run_id"] == "run-1"
    assert rec["agent_slug"] == "sa-discovery"
    assert rec["attempt"] == 2
    assert rec["correlation_id"] == "emit-cid-xyz"


def test_emit_agent_run_completed(with_cid, captured_logs):
    emit_agent_run_completed("run-2", "success", duration_s=4.5)
    rec = _find(_parse_lines(captured_logs), "agent_run.completed")
    assert rec["run_id"] == "run-2"
    assert rec["status"] == "success"
    assert rec["duration_s"] == 4.5
    assert rec["correlation_id"] == "emit-cid-xyz"


def test_emit_approval_requested(with_cid, captured_logs):
    emit_approval_requested("appr-1", "send_outreach", leads=3)
    rec = _find(_parse_lines(captured_logs), "approval.requested")
    assert rec["approval_id"] == "appr-1"
    assert rec["action"] == "send_outreach"
    assert rec["leads"] == 3
    assert rec["correlation_id"] == "emit-cid-xyz"


def test_emit_approval_resolved(with_cid, captured_logs):
    emit_approval_resolved("appr-2", "approved", by="hamed")
    rec = _find(_parse_lines(captured_logs), "approval.resolved")
    assert rec["approval_id"] == "appr-2"
    assert rec["status"] == "approved"
    assert rec["by"] == "hamed"
    assert rec["correlation_id"] == "emit-cid-xyz"


def test_emit_helpers_without_correlation_id(captured_logs):
    """No correlation id in context → field is absent, not 'None'."""
    correlation_id_var.set(None)
    emit_job_started("job-nocid", "default")
    rec = _find(_parse_lines(captured_logs), "job.started")
    assert rec["job_id"] == "job-nocid"
    assert "correlation_id" not in rec


# ---------------------------------------------------------------------------
# Public API surface (the import the parent will rely on)
# ---------------------------------------------------------------------------


def test_public_api_surface_is_importable():
    from lead_engine.observability import (  # noqa: F401
        CorrelationIdMiddleware,
        emit_job_started,
        get_logger,
    )

    assert callable(get_logger)
    assert callable(emit_job_started)
    assert callable(CorrelationIdMiddleware)


# ---------------------------------------------------------------------------
# Format toggle — ``LOG_FORMAT=text`` swaps to the human-readable line.
# ---------------------------------------------------------------------------


def test_text_format_emits_non_json(monkeypatch):
    from lead_engine.observability import logger as logger_mod

    logger_mod.reset_logger_state()
    monkeypatch.setenv("LOG_FORMAT", "text")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(logger_mod.TextFormatter())
    handler.setLevel(logging.DEBUG)

    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)

    try:
        token = set_correlation_id("text-cid")
        log = get_logger("test.text")
        log.info("plain message", route="/x")
        correlation_id_var.reset(token)
    finally:
        root.removeHandler(handler)
        logger_mod.reset_logger_state()

    raw = buffer.getvalue().strip()
    assert raw, "expected at least one log line"
    assert "plain message" in raw
    assert "INFO" in raw
    assert "text-cid" in raw  # correlation id appears in the text line
    # Must NOT be parseable as a single JSON object.
    with pytest.raises(json.JSONDecodeError):
        json.loads(raw.splitlines()[0])
