"""V6 worker entrypoint: python -m apps.worker [--queues default] [--cycles N]

One binary, many subscriptions (ADR-0008/§38). Every loop: lease reaper,
outbox relay tick, doctor heartbeat + alerts (all idempotent).
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lead-engine-v6-worker")
    parser.add_argument("--queues", default="default", help="comma-separated queue subscriptions")
    parser.add_argument("--cycles", type=int, default=None, help="run N cycles then exit (dev)")
    parser.add_argument("--worker-id", default=None)
    args = parser.parse_args(argv)

    from v6api.dependencies import Container
    from application.handlers.pipeline import AcquisitionPipelineHandler
    from infrastructure.config import MIGRATIONS_DIR, Settings
    from infrastructure.doctor.registry import build_doctor
    from infrastructure.events.relay import OutboxRelay
    from infrastructure.events.webhook_consumer import WebhookDispatchConsumer
    from infrastructure.pii.vault import PiiVault
    from infrastructure.postgres.pool import Database
    from infrastructure.providers.bootstrap import build_gateway, build_model_gateway
    from infrastructure.repos.doctor_repo import DoctorRepo
    from infrastructure.uow import PgUowFactory
    from runtime.worker import Worker

    # Legacy credential hydration: the operator's real keys live in the
    # legacy encrypted credential store — reuse it instead of duplicating.
    try:
        from lead_engine.db import open_db as _legacy_open_db
        from lead_engine.secrets import hydrate_environment as _hydrate

        _hydrate(_legacy_open_db(), os.environ.get("LEAD_ENGINE_ORG_ID"))
    except Exception:
        pass  # tests / V6-only environments have no legacy store

    settings = Settings.load()
    db = Database(settings.database_url)
    vault = PiiVault(db, settings)
    gateway = build_gateway()
    model_gateway = build_model_gateway()
    doctor = build_doctor(DoctorRepo(db, MIGRATIONS_DIR), vault=vault,
                          gateway=gateway, model_gateway=model_gateway)

    container = Container(
        settings=settings, db=db, vault=vault, gateway=gateway,
        model_gateway=model_gateway, doctor=doctor,
        handlers={"acquisition.run": AcquisitionPipelineHandler()},
        relay=OutboxRelay(
            db, consumer=WebhookDispatchConsumer(db, settings.master_key),
            batch_size=settings.relay_batch_size),
    )
    uows = PgUowFactory(db, vault_engine=vault)

    worker_id = args.worker_id or f"worker-{uuid.uuid4().hex[:8]}"
    worker = Worker(
        db, settings, container.handlers,
        queues=[q.strip() for q in args.queues.split(",") if q.strip()],
        worker_id=worker_id,
        gateway=container.gateway, model_gateway=container.model_gateway,
        relay=container.relay, uow_factory=uows, doctor=container.doctor,
    )
    print(f"v6 worker up: queues={worker._queues} id={worker_id}")
    try:
        worker.run(max_cycles=args.cycles)
    except KeyboardInterrupt:
        pass
    finally:
        # No heartbeat here on purpose: run_maintenance writes one every tick
        # while the worker is ALIVE. Writing one in finally would report a
        # crashed worker as healthy.
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
