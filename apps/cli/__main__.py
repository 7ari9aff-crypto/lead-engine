"""Operator entrypoints (apps.cli): migrate the database, seed demo data."""
from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lead-engine-v6", description="Lead Engine V6 control CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("migrate", help="apply pending migrations (the only schema path)")
    seed = sub.add_parser("seed", help="seed demo org for local development")
    seed.add_argument("--org-slug", default="demo")

    args = parser.parse_args(argv)

    from infrastructure.config import MIGRATIONS_DIR, Settings

    settings = Settings.load()

    if args.cmd == "migrate":
        from infrastructure.postgres.migrations import apply_migrations

        applied = apply_migrations(settings.database_url, MIGRATIONS_DIR)
        print("applied:", ", ".join(applied) if applied else "database up to date")
        return 0

    if args.cmd == "seed":
        from application.usecases.onboard import OnboardOrg
        from infrastructure.postgres.pool import Database
        from infrastructure.repos.system import BootstrapPg

        db = Database(settings.database_url)
        try:
            result = OnboardOrg(BootstrapPg(db)).execute(
                slug=args.org_slug, name="Demo Org", plan_code="pro",
                owner_ext_id="local-dev-owner"
            )
            print(f"org {result['org_id']} ready (plan pro)")
        finally:
            db.close()
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
