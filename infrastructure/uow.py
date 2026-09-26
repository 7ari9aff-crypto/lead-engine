"""UnitOfWork: one tenant-scoped transaction exposing repositories, the PII
vault and outbox emission — atomicity between business mutation and events is
structural (ADR-0005). PgUowFactory is the application-facing factory."""
from __future__ import annotations

import psycopg

from application.ports import JobContext, Repositories
from contracts.events import EventEnvelope, serialize
from infrastructure.repos.core import (
    AcquisitionRepo,
    ClaimsRepo,
    CompanyRepo,
    ContactsRepo,
    IntelligenceRepo,
    PlatformRepo,
)
from infrastructure.repos.governance_projects import (
    GovernanceRepo,
    LineageRepo,
    ProjectsRepo,
)


class _Repos:
    def __init__(self, cur: psycopg.Cursor):
        self.platform = PlatformRepo(cur)
        self.acquisition = AcquisitionRepo(cur)
        self.companies = CompanyRepo(cur)
        self.claims = ClaimsRepo(cur)
        self.contacts = ContactsRepo(cur)
        self.intelligence = IntelligenceRepo(cur)
        self.governance = GovernanceRepo(cur)
        self.projects = ProjectsRepo(cur)
        self.lineage = LineageRepo(cur)


class PgUnitOfWork:
    """``with uow(org) as tx: tx.repos... ; tx.emit(event)``"""

    def __init__(self, db, tenant_id: str, vault_engine=None):
        self._db = db
        self._tenant = tenant_id
        self._vault_engine = vault_engine
        self._conn: psycopg.Connection | None = None
        self._repos: _Repos | None = None

    def __enter__(self):
        # IMPORTANT: keep the pool's connection context manager alive for the
        # whole unit of work. Creating + entering it inline lets the discarded
        # CM be garbage-collected, which returns the connection to the pool
        # mid-transaction (observed as app.tenant_id silently resetting).
        self._cm = self._db._pool.connection()
        self._conn = self._cm.__enter__()
        with self._conn.cursor() as cur:
            cur.execute("SELECT set_config('app.tenant_id', %s, true)", (self._tenant,))
        self._repos = _Repos(self._conn.cursor())
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if getattr(self, "_cm", None) is not None:
            self._cm.__exit__(exc_type, exc, tb)
            self._cm = None
            self._conn = None
            self._repos = None

    @property
    def repos(self) -> Repositories:
        assert self._repos is not None, "unitOfWork not entered"
        return self._repos  # type: ignore[return-value]

    @property
    def cursor(self) -> psycopg.Cursor:
        """Cursor on the current transaction — for gateway ledger operations
        that must commit atomically with the business writes they accompany."""
        assert self._conn is not None, "unitOfWork not entered"
        return self._conn.cursor()

    @property
    def vault(self):
        from infrastructure.pii.vault import TenantVault

        assert self._vault_engine is not None, "no vault configured"
        return TenantVault(self._vault_engine, self._tenant)

    def emit(self, event: EventEnvelope) -> None:
        """Write an event into the outbox on the CURRENT transaction."""
        assert self._conn is not None, "unitOfWork not entered"
        row = event.to_row()
        with self._conn.cursor() as cur:
            cur.execute(
                """INSERT INTO events.outbox
                     (event_id, version, type, aggregate_type, aggregate_id, org_id,
                      producer, trace_id, correlation_id, causation_id, payload)
                   VALUES (%(event_id)s, %(version)s, %(type)s, %(aggregate_type)s,
                           %(aggregate_id)s, %(org_id)s, %(producer)s, %(trace_id)s,
                           %(correlation_id)s, %(causation_id)s, %(payload)s)""",
                {**row, "payload": psycopg.types.json.Json(serialize(row["payload"]))},
            )


class JobUnitOfWork(PgUnitOfWork):
    """UnitOfWork correlated with the current job attempt."""

    def __init__(self, db, tenant_id: str, job: JobContext, vault_engine=None):
        super().__init__(db, tenant_id, vault_engine)
        self._job = job

    def emit(self, event: EventEnvelope) -> None:
        correlated = EventEnvelope(
            type=event.type,
            aggregate_type=event.aggregate_type,
            aggregate_id=event.aggregate_id,
            org_id=event.org_id or self._job.org_id,
            payload=event.payload,
            version=event.version,
            producer=event.producer,
            trace_id=event.trace_id or self._job.lease_token or None,
            correlation_id=event.correlation_id or self._job.job_id,
            causation_id=event.causation_id,
        )
        super().emit(correlated)


class PgUowFactory:
    """The UowFactory port — one place creates units of work."""

    def __init__(self, db, vault_engine=None):
        self._db = db
        self._vault_engine = vault_engine

    def __call__(self, org_id: str, job: JobContext | None = None):
        if job is not None:
            return JobUnitOfWork(self._db, org_id, job, vault_engine=self._vault_engine)
        return PgUnitOfWork(self._db, org_id, vault_engine=self._vault_engine)
