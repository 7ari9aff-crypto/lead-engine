"""Structured logger — stdlib ``logging`` with JSON output.

A small wrapper that:

* picks the level from the ``LOG_LEVEL`` env var (default ``INFO``),
* picks the format from ``LOG_FORMAT``: ``"json"`` (default) emits one JSON
  object per record, ``"text"`` emits a human-readable line,
* merges any ``extra={...}`` kwargs passed to ``.info()`` / ``.warning()`` /
  ``.error()`` / ``.debug()`` into the JSON payload,
* stamps every record with the current correlation id (from
  :data:`lead_engine.observability.context.correlation_id_var`) when one
  is set, and
* is process-global via :func:`get_logger` (the underlying handlers are
  attached once, never duplicated).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Mapping


# ---------------------------------------------------------------------------
# Configuration via environment variables.
# ---------------------------------------------------------------------------

_DEFAULT_LEVEL = "INFO"
_DEFAULT_FORMAT = "json"
_VALID_LEVELS = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
    "NOTSET": logging.NOTSET,
}


def _coerce_log_level(raw: str | None) -> int:
    if not raw:
        return _VALID_LEVELS[_DEFAULT_LEVEL]
    return _VALID_LEVELS.get(raw.strip().upper(), _VALID_LEVELS[_DEFAULT_LEVEL])


def _coerce_log_format(raw: str | None) -> str:
    if not raw:
        return _DEFAULT_FORMAT
    val = raw.strip().lower()
    return val if val in ("json", "text") else _DEFAULT_FORMAT


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


# Keys that the stdlib ``logging`` module reserves on every ``LogRecord``;
# everything else is treated as application-supplied "extra" data.
_STDLOG_RESERVED = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "asctime", "taskName",
}


class JsonFormatter(logging.Formatter):
    """Emit each :class:`logging.LogRecord` as a single JSON object.

    The shape is:

    .. code-block:: json

        {
          "timestamp": "2026-09-11T14:51:29.123+00:00",
          "level": "INFO",
          "logger": "lead_engine.api.app",
          "message": "...",
          "correlation_id": "...",        // only if set in context
          ... plus any extra fields ...
        }
    """

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        # Build a base payload. ``getMessage`` runs the %-formatting that the
        # caller may have passed positionally; we always prefer the rendered
        # message in ``message``.
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add correlation id from the context var, but only when set. We
        # import here to avoid a circular import at module load time.
        try:
            from .context import get_correlation_id

            cid = get_correlation_id()
        except Exception:
            cid = None
        if cid:
            payload["correlation_id"] = cid

        # Merge in any extra fields the caller attached.
        for key, value in record.__dict__.items():
            if key in _STDLOG_RESERVED or key.startswith("_"):
                continue
            # Don't clobber the keys we just set explicitly.
            if key in payload:
                continue
            payload[key] = _jsonable(value)

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)

        # ``default=str`` is a safety net — if an "extra" field contains
        # something that isn't natively JSON-serializable (e.g. a UUID or a
        # dataclass), we render it as a string rather than crashing the
        # logging pipeline.
        return json.dumps(payload, default=str, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    """A human-friendly fallback formatter used when ``LOG_FORMAT=text``.

    Includes the correlation id (when present) so log lines remain
    correlatable across services without forcing operators to parse JSON.
    """

    DEFAULT_FORMAT = (
        "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    )

    def __init__(self) -> None:
        super().__init__(self.DEFAULT_FORMAT)

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        try:
            from .context import get_correlation_id

            cid = get_correlation_id()
        except Exception:
            cid = None
        if cid:
            return f"{base} [cid={cid}]"
        return base


# ---------------------------------------------------------------------------
# Process-global handler installation.
# ---------------------------------------------------------------------------

_handler_lock = __import__("threading").Lock()
_handler_installed = False
_active_handler: logging.Handler | None = None
_active_level: int | None = None
_active_format: str | None = None


def _install_handler_once() -> None:
    """Attach a stderr StreamHandler with the configured formatter.

    Idempotent — only the *first* call to :func:`get_logger` (per process)
    wires a handler onto the root logger. Subsequent calls reuse the same
    handler so we don't multiply log lines when many components ask for a
    logger at import time.
    """
    global _handler_installed, _active_handler, _active_level, _active_format

    level = _coerce_log_level(os.environ.get("LOG_LEVEL"))
    fmt = _coerce_log_format(os.environ.get("LOG_FORMAT"))

    with _handler_lock:
        if _handler_installed and _active_handler is not None:
            # Allow live tuning via env var updates between test runs.
            if _active_level != level:
                _active_handler.setLevel(level)
                _active_level = level
            if _active_format != fmt:
                _active_handler.setFormatter(
                    JsonFormatter() if fmt == "json" else TextFormatter()
                )
                _active_format = fmt
            return

        handler: logging.Handler = logging.StreamHandler(stream=sys.stderr)
        handler.setLevel(level)
        handler.setFormatter(
            JsonFormatter() if fmt == "json" else TextFormatter()
        )

        root = logging.getLogger()
        # Don't override an operator-installed handler if one is already
        # attached with a non-default level — but still ensure propagation
        # works for our own named loggers.
        if not root.handlers:
            root.addHandler(handler)
            root.setLevel(level)
        else:
            # Append; the operator's setup wins for formatting. We still
            # ensure the root level is at least as permissive as our env.
            if root.level == logging.NOTSET or root.level > level:
                root.setLevel(level)

        _handler_installed = True
        _active_handler = handler
        _active_level = level
        _active_format = fmt


def reset_logger_state() -> None:
    """Test hook — drop the cached handler so the next :func:`get_logger`
    call re-installs from current env vars."""
    global _handler_installed, _active_handler, _active_level, _active_format
    with _handler_lock:
        root = logging.getLogger()
        if _active_handler is not None and _active_handler in root.handlers:
            root.removeHandler(_active_handler)
        _handler_installed = False
        _active_handler = None
        _active_level = None
        _active_format = None


# ---------------------------------------------------------------------------
# StructuredLogger wrapper
# ---------------------------------------------------------------------------


def _jsonable(value: Any) -> Any:
    """Best-effort coercion of arbitrary values into JSON-friendly types."""
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(v) for v in value]
    return str(value)


class StructuredLogger:
    """Thin convenience wrapper around :class:`logging.Logger`.

    The wrapper forwards ``.info()`` / ``.warning()`` / ``.error()`` /
    ``.debug()`` to the underlying logger while treating trailing ``**extra``
    kwargs as structured fields. The resulting JSON line includes them as
    top-level keys alongside ``message`` and ``correlation_id``.
    """

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    # ---- introspection -------------------------------------------------

    @property
    def raw(self) -> logging.Logger:
        """Escape hatch — return the underlying stdlib logger."""
        return self._logger

    @property
    def name(self) -> str:
        return self._logger.name

    # ---- logging methods -----------------------------------------------

    def debug(self, message: str, *args: Any, **extra: Any) -> None:
        self._log(logging.DEBUG, message, args, extra)

    def info(self, message: str, *args: Any, **extra: Any) -> None:
        self._log(logging.INFO, message, args, extra)

    def warning(self, message: str, *args: Any, **extra: Any) -> None:
        self._log(logging.WARNING, message, args, extra)

    def error(self, message: str, *args: Any, **extra: Any) -> None:
        self._log(logging.ERROR, message, args, extra)

    def exception(
        self,
        message: str,
        *args: Any,
        exc_info: bool = True,
        **extra: Any,
    ) -> None:
        """Log ``message`` at ERROR level, attaching current exception info."""
        self._log(logging.ERROR, message, args, extra, exc_info=exc_info)

    # ---- internal ------------------------------------------------------

    def _log(
        self,
        level: int,
        message: str,
        args: tuple[Any, ...],
        extra: Mapping[str, Any],
        exc_info: Any = False,
    ) -> None:
        # ``logging.Logger.log`` accepts ``extra={...}`` and merges it into
        # the record's __dict__. We copy to avoid leaking the caller's dict.
        merged: dict[str, Any] = dict(extra) if extra else {}
        self._logger.log(
            level,
            message,
            *args,
            extra=merged,
            exc_info=exc_info,
        )


def get_logger(name: str) -> StructuredLogger:
    """Return a :class:`StructuredLogger` for the given dotted name.

    Idempotent: calling with the same name twice returns wrappers around the
    same underlying :class:`logging.Logger`. The first call also installs
    the process-wide stderr handler configured via ``LOG_LEVEL`` /
    ``LOG_FORMAT``.
    """
    _install_handler_once()
    return StructuredLogger(logging.getLogger(name))


__all__ = [
    "StructuredLogger",
    "JsonFormatter",
    "TextFormatter",
    "get_logger",
    "reset_logger_state",
]
