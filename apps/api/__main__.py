"""V6 API entrypoint: python -m apps.api [--port 8002]

Composition root: builds the container with real infrastructure (Supabase
Postgres, PII vault, fake providers until real adapters are enabled).
"""
from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lead-engine-v6-api")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8002)
    args = parser.parse_args(argv)

    import uvicorn

    from api.app import create_app
    from api.dependencies import Container
    from application.handlers.pipeline import AcquisitionPipelineHandler
    from infrastructure.config import Settings
    from infrastructure.events.relay import OutboxRelay
    from infrastructure.models.gateway import FakeModel, ModelGateway
    from infrastructure.pii.vault import PiiVault
    from infrastructure.postgres.pool import Database
    from infrastructure.providers.fakes import FakeSearchProvider, FakeVerifyProvider
    from infrastructure.providers.gateway import ProviderGateway

    settings = Settings.load()
    db = Database(settings.database_url)
    vault = PiiVault(db, settings)

    gateway = ProviderGateway()
    gateway.register(FakeSearchProvider("fake-search", priority=10, results=[]))
    gateway.register(FakeVerifyProvider("fake-verify", priority=10))

    model_gateway = ModelGateway()
    model_gateway.register("planning", FakeModel())

    container = Container(
        settings=settings, db=db, vault=vault, gateway=gateway,
        model_gateway=model_gateway,
        handlers={"acquisition.run": AcquisitionPipelineHandler()},
        relay=OutboxRelay(db, consumer=lambda event: None,
                          batch_size=settings.relay_batch_size),
    )
    uvicorn.run(create_app(container), host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
