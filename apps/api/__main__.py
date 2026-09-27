"""V6 API entrypoint: python -m apps.api [--port 8002]

Composition root: builds the container with real infrastructure (Supabase
Postgres, PII vault, fake providers until real adapters are enabled).
"""
from __future__ import annotations

import argparse
import os
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lead-engine-v6-api")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8002)
    args = parser.parse_args(argv)

    import uvicorn

    from v6api.app import create_app
    from v6api.dependencies import Container
    from application.handlers.pipeline import AcquisitionPipelineHandler
    from infrastructure.config import Settings
    from infrastructure.events.relay import OutboxRelay
    from infrastructure.pii.vault import PiiVault
    from infrastructure.postgres.pool import Database

    settings = Settings.load()
    db = Database(settings.database_url)
    vault = PiiVault(db, settings)

    # Legacy credential hydration: the operator's real keys live in the
    # legacy encrypted credential store — reuse it instead of duplicating.
    try:
        from lead_engine.db import open_db as _legacy_open_db
        from lead_engine.secrets import hydrate_environment as _hydrate

        _hydrate(_legacy_open_db(), os.environ.get("LEAD_ENGINE_ORG_ID"))
    except Exception:
        pass  # tests / V6-only environments have no legacy store

    from infrastructure.providers.bootstrap import build_gateway

    gateway = build_gateway()

    from infrastructure.providers.bootstrap import build_model_gateway

    model_gateway = build_model_gateway()

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
