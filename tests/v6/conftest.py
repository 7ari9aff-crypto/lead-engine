"""V6 test suite fixtures.

The suite runs against the Supabase Postgres directly (operator decision —
no local Docker). Session start wipes ONLY the dedicated V6 schemas and
re-applies migrations; legacy schemas (public/engine/activity) are never
touched.
"""
from __future__ import annotations

import uuid

import pytest

from infrastructure.config import MIGRATIONS_DIR, Settings
from infrastructure.pii.vault import PiiVault
from infrastructure.postgres.migrations import apply_migrations
from infrastructure.postgres.pool import Database
from infrastructure.providers.fakes import (
    FakeContactProvider,
    FakeSearchProvider,
    FakeVerifyProvider,
)
from infrastructure.providers.gateway import ProviderGateway
from infrastructure.uow import PgUowFactory

V6_SCHEMAS = [
    "platform", "acquisition", "company_identity", "claims_evidence",
    "contacts", "intelligence", "governance", "projects", "pii",
    "runtime", "events", "effects", "agents",
]


def _wipe_v6_schemas(settings: Settings) -> None:
    """Drop ONLY the V6-owned schemas. Refuses anything else by construction."""
    from infrastructure.postgres.supabase_api import SupabaseSqlClient
    import os

    client = None
    token = os.environ.get("LEAD_ENGINE_V6_SUPABASE_ACCESS_TOKEN", "")
    ref = os.environ.get("SUPABASE_PROJECT_REF", "")
    if token and ref:
        client = SupabaseSqlClient(token, ref)
        for schema in V6_SCHEMAS:
            client.query(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE;')
        client.close()
        return
    # fallback: local role with DDL rights
    import psycopg

    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        for schema in V6_SCHEMAS:
            conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


@pytest.fixture(scope="session")
def settings() -> Settings:
    # The legacy tests/conftest.py blanks SUPABASE_DB_URL in os.environ to
    # protect its fixtures; V6 re-reads .env so the operator's Supabase DSN
    # applies. Pop the blanks first (load_env never overwrites).
    import os

    for key in ("SUPABASE_DB_URL", "DATABASE_URL", "LEAD_ENGINE_V6_DATABASE_URL"):
        os.environ.pop(key, None)
    return Settings.load()


@pytest.fixture(scope="session")
def migrated_db(settings: Settings) -> Database:
    _wipe_v6_schemas(settings)
    apply_migrations(settings.database_url, MIGRATIONS_DIR)
    db = Database(settings.database_url)
    yield db
    db.close()


@pytest.fixture()
def db(migrated_db: Database) -> Database:
    return migrated_db


@pytest.fixture()
def vault(settings: Settings, db: Database) -> PiiVault:
    return PiiVault(db, settings)


@pytest.fixture()
def uows(db: Database, vault: PiiVault) -> PgUowFactory:
    return PgUowFactory(db, vault_engine=vault)


@pytest.fixture()
def org(uows: PgUowFactory) -> str:
    """A fresh organization (pro plan) per test."""
    from application.usecases.onboard import OnboardOrg
    from infrastructure.repos.system import BootstrapPg

    db = uows._db
    slug = f"org-{uuid.uuid4().hex[:10]}"
    result = OnboardOrg(BootstrapPg(db)).execute(slug, "Test Org", "pro",
                                                 f"owner-{uuid.uuid4().hex[:8]}")
    return result["org_id"]


@pytest.fixture()
def free_org(org: str, db: Database) -> str:
    """Switch the test org to the free plan (1 concurrent job, low caps)."""
    with db.tx(org) as conn, conn.cursor() as cur:
        cur.execute("UPDATE platform.organizations SET plan_code = 'free' WHERE id = %s",
                    (org,))
    return org


@pytest.fixture()
def fake_gateway() -> tuple[ProviderGateway, dict[str, object]]:
    """Gateway with deterministic fakes + the objects for assertions."""
    search = FakeSearchProvider("fake-search", priority=10, cost=1)
    verify = FakeVerifyProvider(
        "fake-verify", priority=10,
        mapping={"info@alpha-dental.sa": "DELIVERABLE",
                 "office@beta-clinic.sa": "CATCH_ALL"},
    )
    contact = FakeContactProvider(
        contacts_by_domain={
            "alpha-dental.sa": [{"name": "Dr. Sara", "role": "owner",
                                 "email": "info@alpha-dental.sa", "phone": "+966500000001"}],
            "beta-clinic.sa": [{"name": "Mr. Khaled", "role": "manager",
                                "email": "office@beta-clinic.sa"}],
        },
    )
    gateway = ProviderGateway()
    gateway.register(search)
    gateway.register(verify)
    gateway.register(contact)
    return gateway, {"search": search, "verify": verify, "contact": contact}


SAMPLE_ICP = {
    "name": "saudi-dental",
    "country": "SA",
    "industry": "dental",
    "cities": [{"name": "Riyadh", "ar": "الرياض"}],
    "keywords_en": ["dental clinic"],
    "keywords_ar": [],
    "v0_limits": {"max_search_queries": 2, "search_results_per_query": 4},
}


def seed_results(search: FakeSearchProvider) -> None:
    """Two real businesses (one shared across queries), a social page, and an
    editorial listicle — identity resolution must keep only the businesses."""
    search._results = [
        {"match": "dental clinic in Riyadh", "always": True,
         "url": "https://alpha-dental.sa", "title": "Alpha Dental Clinic",
         "snippet": "dental clinic in Riyadh"},
        {"match": "dental clinic in Riyadh", "always": True,
         "url": "https://beta-clinic.sa/en", "title": "Beta Clinic",
         "snippet": "dental services"},
        {"match": "dental clinic in Riyadh", "always": True,
         "url": "https://facebook.com/riyadh-dental", "title": "Dental page",
         "snippet": "social"},
        {"match": "dental clinic in Riyadh", "always": True,
         "url": "https://news.example.com/best-dental", "title": "Best dental clinics 2026",
         "snippet": "article"},
    ]


@pytest.fixture()
def worker_factory(db: Database, settings: Settings, uows: PgUowFactory):
    from runtime.worker import Worker

    def _make(handlers: dict, gateway: ProviderGateway, relay=None,
              queues: list[str] | None = None, worker_id: str = "test-worker") -> Worker:
        return Worker(
            db, settings, handlers,
            queues=queues or ["default"], worker_id=worker_id,
            gateway=gateway, relay=relay, uow_factory=uows,
        )

    return _make
