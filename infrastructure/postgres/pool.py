"""Pooled Postgres access with pooler-safe tenant scoping (ADR-0002).

Two transaction flavours:

- ``tx(tenant_id=...)`` — business truth. Runs ``SET LOCAL app.tenant_id`` so
  FORCE RLS policies scope every statement to the tenant. Fail-closed: without
  a tenant the policies deny every row.
- ``tx_system()`` — runtime/system plane (jobs, outbox, effects). Cross-tenant
  by design; never touches tenant-owned business tables directly.

Connections are pooled; ``SET LOCAL`` lives inside the transaction, so nothing
leaks across pool re-use.
"""
from __future__ import annotations

import contextlib
from collections.abc import Iterator
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


class Database:
    def __init__(self, dsn: str, min_size: int = 1, max_size: int = 8):
        self._pool = ConnectionPool(
            dsn,
            min_size=min_size,
            max_size=max_size,
            kwargs={"row_factory": dict_row, "autocommit": False},
            open=True,
            check=psycopg_pool.ConnectionPool.check_connection,
        )

    def close(self) -> None:
        self._pool.close()

    @contextlib.contextmanager
    def tx(self, tenant_id: str | None = None) -> Iterator[psycopg.Connection]:
        """Business transaction. Pass tenant_id for tenant-scoped work."""
        with self._pool.connection() as conn:
            if tenant_id is not None:
                with conn.cursor() as cur:
                    cur.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))
            yield conn

    @contextlib.contextmanager
    def tx_system(self) -> Iterator[psycopg.Connection]:
        """System-plane transaction (runtime.jobs, events, effects)."""
        with self._pool.connection() as conn:
            yield conn

    def one(self, tenant_id: str | None, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        with self.tx(tenant_id) as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()

    def query(self, tenant_id: str | None, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        with self.tx(tenant_id) as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())

    def execute(self, tenant_id: str | None, sql: str, params: tuple = ()) -> str:
        with self.tx(tenant_id) as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.statusmessage or ""


# psycopg_pool ships the pool class; import kept at module level for check=.
import psycopg_pool  # noqa: E402  (used in Database.__init__ default)
