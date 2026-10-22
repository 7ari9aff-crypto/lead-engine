"""Asynchronous Manus discovery stage (ADR-0011).

Runs inside ``acquisition.run`` ONLY when the ICP asks for it
(``discovery.engine == "manus"``). It never holds a database transaction while
waiting: submitting, polling and fetching company sites happen outside any unit
of work; a short unit of work is opened only to ingest verified companies.

While Manus is still working the stage parks the job (no attempt burned) and the
worker's maintenance tick wakes it about once a minute. All progress lives in the
checkpoint, so a restarted worker carries on without paying for a task twice.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from application.ports import JobContext, JobOps
from contracts.errors import DomainError

log = logging.getLogger(__name__)

STAGE_KEY = "manus"


@dataclass
class ManusStageConfig:
    """Everything the stage needs, injected (no vendor import in this layer).

    ``ledger_factory(snapshot|None)`` -> a KeyLedger, ``client_factory(key)`` ->
    an object with create_task/task_detail/final_answer, ``fetch(url)`` -> page
    HTML or None.
    """
    ledger_factory: Callable[[dict | None], Any]
    client_factory: Callable[[str], Any]
    fetch: Callable[[str], str | None]
    per_city: int = 15
    engine_factory: Callable[..., Any] | None = None
    verify: Callable[..., dict] | None = None


def wants_manus(icp_snapshot: dict[str, Any]) -> bool:
    return str((icp_snapshot.get("discovery") or {}).get("engine", "")).lower() == "manus"


def run_stage(handler, ctx: JobContext, ops: JobOps, ck: dict[str, Any],
              cfg: ManusStageConfig | None) -> dict[str, Any] | str:
    """Advance the Manus stage. Returns the updated checkpoint when finished,
    or ``"PARKED"`` after parking the job to wait for Manus."""
    if cfg is None:
        raise DomainError(
            "discovery.engine is 'manus' but no Manus key is configured "
            "(save MANUS_API_KEY in Settings)")

    from infrastructure.providers.manus import verify_company
    from infrastructure.providers.manus_engine import ManusDiscovery

    verify = cfg.verify or verify_company
    state = dict(ck.get(STAGE_KEY) or {})
    try:
        ledger = cfg.ledger_factory(state.get("ledger"))
    except RuntimeError as exc:                      # e.g. MANUS_API_KEY not set
        raise DomainError(
            f"discovery.engine is 'manus' but {exc} (save MANUS_API_KEY in Settings)") from exc
    make = cfg.engine_factory or ManusDiscovery
    engine = make(ledger=ledger, client_factory=cfg.client_factory, state=state or None)

    icp = ck["icp"]
    engine.submit(icp, per_city=cfg.per_city)
    # persist task ids BEFORE anything else: a crash after this never re-pays
    ck = {**ck, STAGE_KEY: engine.state()}
    ops.checkpoint(ck)

    if engine.exhausted and engine.pending == 0 and not state.get("companies_seen"):
        raise DomainError("manus: every key is at or under the credit floor; nothing submitted")

    polled = engine.poll()
    verified = [verify(c, fetch=cfg.fetch) for c in polled.companies]   # HTTP, no tx open
    ck = {**ck, STAGE_KEY: {**engine.state(),
                            "companies_seen": state.get("companies_seen", 0) + len(verified)}}
    ops.checkpoint(ck)

    if verified:
        company_ids = list(ck.get("company_ids", []))
        with ops.uow() as tx:
            for company in verified:
                cid = handler._ingest_manus_company(tx, ctx, ck, company)
                if cid and cid not in company_ids:
                    company_ids.append(cid)
        ck = {**ck, "company_ids": company_ids}
        ops.checkpoint(ck)

    if not polled.finished:
        if ops.cancel_requested():
            return ck
        ops.park(f"waiting on manus ({engine.pending} task(s) running)")
        return "PARKED"
    return ck
