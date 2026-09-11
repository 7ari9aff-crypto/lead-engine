"""Typed event emitters.

Each helper in this module wraps a :class:`StructuredLogger` and stamps a
``kind=`` field so downstream log pipelines can filter on the event type
without parsing the message string. Every emission pulls the current
correlation id out of the context var, so events emitted from anywhere
inside a request handler are automatically linked to the request that
spawned them.

These helpers are intentionally side-effect free with respect to the
business state — they only emit logs. Wiring them into actual lifecycle
points is the parent module's job.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from .context import get_correlation_id
from .logger import StructuredLogger, get_logger


# ---------------------------------------------------------------------------
# Per-event loggers. Using distinct logger names keeps the event streams
# individually filterable (e.g. ``events.job``, ``events.agent``).
# ---------------------------------------------------------------------------

_JOB_LOGGER_NAME = "events.job"
_AGENT_LOGGER_NAME = "events.agent"
_APPROVAL_LOGGER_NAME = "events.approval"


def _emit(
    logger: StructuredLogger,
    kind: str,
    payload: Mapping[str, Any],
) -> None:
    """Stamp ``kind`` + ``correlation_id`` onto *payload* and emit it."""
    merged: dict[str, Any] = {"kind": kind}
    cid = get_correlation_id()
    if cid is not None:
        merged["correlation_id"] = cid
    for k, v in payload.items():
        # ``kind`` / ``correlation_id`` win over caller-supplied keys.
        if k in merged:
            continue
        merged[k] = v
    # Single combined message + extras so the JSON line groups cleanly.
    logger.info(f"event={kind}", **merged)


# ---------------------------------------------------------------------------
# Job lifecycle
# ---------------------------------------------------------------------------


def emit_job_started(job_id: str, icp: str, **extra: Any) -> None:
    """Log a ``job.started`` event."""
    _emit(
        get_logger(_JOB_LOGGER_NAME),
        kind="job.started",
        payload={"job_id": job_id, "icp": icp, **extra},
    )


def emit_job_completed(
    job_id: str,
    state: str,
    metrics: Optional[dict] = None,
    **extra: Any,
) -> None:
    """Log a ``job.completed`` event (state is e.g. ``COMPLETED`` / ``PAUSED``)."""
    payload: dict[str, Any] = {"job_id": job_id, "state": state}
    if metrics is not None:
        payload["metrics"] = dict(metrics)
    payload.update(extra)
    _emit(
        get_logger(_JOB_LOGGER_NAME),
        kind="job.completed",
        payload=payload,
    )


def emit_job_paused(job_id: str, reason: str, **extra: Any) -> None:
    """Log a ``job.paused`` event with the reason it stopped."""
    _emit(
        get_logger(_JOB_LOGGER_NAME),
        kind="job.paused",
        payload={"job_id": job_id, "reason": reason, **extra},
    )


# ---------------------------------------------------------------------------
# Agent runs
# ---------------------------------------------------------------------------


def emit_agent_run_started(run_id: str, agent_slug: str, **extra: Any) -> None:
    """Log an ``agent_run.started`` event."""
    _emit(
        get_logger(_AGENT_LOGGER_NAME),
        kind="agent_run.started",
        payload={"run_id": run_id, "agent_slug": agent_slug, **extra},
    )


def emit_agent_run_completed(run_id: str, status: str, **extra: Any) -> None:
    """Log an ``agent_run.completed`` event (status e.g. ``success`` /
    ``failed``)."""
    _emit(
        get_logger(_AGENT_LOGGER_NAME),
        kind="agent_run.completed",
        payload={"run_id": run_id, "status": status, **extra},
    )


# ---------------------------------------------------------------------------
# Approval workflow
# ---------------------------------------------------------------------------


def emit_approval_requested(approval_id: str, action: str, **extra: Any) -> None:
    """Log an ``approval.requested`` event."""
    _emit(
        get_logger(_APPROVAL_LOGGER_NAME),
        kind="approval.requested",
        payload={"approval_id": approval_id, "action": action, **extra},
    )


def emit_approval_resolved(approval_id: str, status: str, **extra: Any) -> None:
    """Log an ``approval.resolved`` event (status e.g. ``approved`` /
    ``rejected``)."""
    _emit(
        get_logger(_APPROVAL_LOGGER_NAME),
        kind="approval.resolved",
        payload={"approval_id": approval_id, "status": status, **extra},
    )


__all__ = [
    "emit_job_started",
    "emit_job_completed",
    "emit_job_paused",
    "emit_agent_run_started",
    "emit_agent_run_completed",
    "emit_approval_requested",
    "emit_approval_resolved",
]
