"""V6 worker entrypoint: python -m apps.worker [--queues default] [--cycles N]

One binary, many subscriptions (ADR-0008/§38). Also drives the outbox relay
and the lease reaper every loop (both idempotent).
"""
from __future__ import annotations

import argparse
import sys
import uuid


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lead-engine-v6-worker")
    parser.add_argument("--queues", default="default", help="comma-separated queue subscriptions")
    parser.add_argument("--cycles", type=int, default=None, help="run N cycles then exit (dev)")
    parser.add_argument("--worker-id", default=None)
    args = parser.parse_args(argv)

    from api.dependencies import Container
    from application.handlers.pipeline import AcquisitionPipelineHandler
    from infrastructure.config import Settings
    from infrastructure.events.relay import OutboxRelay
    from infrastructure.pii.vault import PiiVault
    from infrastructure.postgres.pool import Database
    from infrastructure.providers.bootstrap import build_gateway
    from infrastructure.uow import PgUowFactory
    from runtime.worker import Worker

    settings = Settings.load()
    db = Database(settings.database_url)
    vault = PiiVault(db, settings)

    gateway = build_gateway()

    container = Container(
        settings=settings, db=db, vault=vault, gateway=gateway, model_gateway=None,
        handlers={"acquisition.run": AcquisitionPipelineHandler()},
        relay=OutboxRelay(db, consumer=lambda event: None,
                          batch_size=settings.relay_batch_size),
    )
    uows = PgUowFactory(db, vault_engine=vault)

    worker = Worker(
        db, settings, container.handlers,
        queues=[q.strip() for q in args.queues.split(",") if q.strip()],
        worker_id=args.worker_id or f"worker-{uuid.uuid4().hex[:8]}",
        gateway=container.gateway, relay=container.relay, uow_factory=uows,
    )
    print(f"v6 worker up: queues={worker._queues} id={worker._worker_id}")
    try:
        worker.run(max_cycles=args.cycles)
    except KeyboardInterrupt:
        pass
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
