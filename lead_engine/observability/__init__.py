"""Lead Engine — observability primitives.

A small structured-logging layer with:

* :class:`StructuredLogger` — a stdlib ``logging`` wrapper that emits JSON
  lines (or human-readable text) and merges any ``extra`` kwargs into the
  output payload.
* ``correlation_id_var`` + :func:`set_correlation_id` / :func:`get_correlation_id`
  — a :mod:`contextvars`-backed correlation id propagated through the request
  lifecycle and stamped onto every log record.
* :class:`CorrelationIdMiddleware` — FastAPI middleware that pulls / generates
  the correlation id and echoes it back on the response.
* :mod:`events` — typed ``emit_*`` helpers for the engine's domain events
  (job started, agent run completed, approval resolved, ...).

The whole module is intentionally dependency-free (stdlib only) so it can
ship with the existing project without touching ``requirements.txt``.
"""

from .context import (
    CorrelationIdMiddleware,
    correlation_id_from_request,
    correlation_id_var,
    get_correlation_id,
    set_correlation_id,
)
from .events import (
    emit_agent_run_completed,
    emit_agent_run_started,
    emit_approval_requested,
    emit_approval_resolved,
    emit_job_completed,
    emit_job_paused,
    emit_job_started,
)
from .logger import StructuredLogger, get_logger

__all__ = [
    # logger
    "StructuredLogger",
    "get_logger",
    # correlation context
    "correlation_id_var",
    "set_correlation_id",
    "get_correlation_id",
    "CorrelationIdMiddleware",
    "correlation_id_from_request",
    # event emitters
    "emit_job_started",
    "emit_job_completed",
    "emit_job_paused",
    "emit_agent_run_started",
    "emit_agent_run_completed",
    "emit_approval_requested",
    "emit_approval_resolved",
]
