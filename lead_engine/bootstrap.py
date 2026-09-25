"""Process-scoped one-shot data bootstrap.

Migrations own schema; this module owns seed rows. It exists because seeding and
DDL were previously executed from per-request constructors, which made every
request pay dozens of sequential round trips (LAT-01) and, where the app role
lacks DDL privileges, guaranteed a 500 on every call.

A step is marked done even when it raises: the request path must never become
slow or failing again because of bootstrap work. Failures are logged loudly and
`python -m lead_engine init` remains the authoritative, retryable path.
"""
import logging
import threading

log = logging.getLogger(__name__)

_lock = threading.Lock()
_done: set[str] = set()


def run_once(name: str, fn) -> bool:
    """Run ``fn`` at most once per process. Returns True if this call ran it."""
    with _lock:
        if name in _done:
            return False
        _done.add(name)
    try:
        fn()
    except Exception as exc:  # never propagate bootstrap trouble
        log.error("bootstrap step %s failed: %s: %s", name, type(exc).__name__, exc)
        return False
    return True


def reset() -> None:
    """Test hook: forget which steps have run."""
    with _lock:
        _done.clear()


def run_data_bootstrap(db) -> None:
    """The startup data steps, shared by every long-lived entry point.

    Call this from a process seam (FastAPI lifespan, worker loop, CLI) and never
    from a request path. Both steps are non-fatal by design: a process must boot
    even when the data layer is unhappy, because `python -m lead_engine init`
    stays the authoritative, retryable path.

    * activity schema - on Postgres migrations own DDL and the app role holds
      `USAGE` but not `CREATE` on `engine`, so this statement is *expected* to
      fail there: logged at info and skipped, never raised.
    * seed rows (providers, agents, tools, connections) - DML only, guarded by
      `run_once`, so a second call in the same process is free.
    """
    from .activity.store import ensure_schema
    from .agent_registry import ensure_seeded

    try:
        ensure_schema(db)
    except Exception as exc:
        log.info("activity schema skipped at startup: %s: %s", type(exc).__name__, exc)
    ensure_seeded(db)
