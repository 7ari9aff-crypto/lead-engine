"""Apply migrations through the Supabase Management API.

Used when the runtime role cannot perform DDL (e.g. the restricted
``lead_engine`` role on Supabase): the API executes SQL as the ``postgres``
role. Requires ``LEAD_ENGINE_V6_SUPABASE_ACCESS_TOKEN`` and
``SUPABASE_PROJECT_REF`` in the environment (or .env).
"""
from __future__ import annotations

import httpx

API_BASE = "https://api.supabase.com/v1"


class SupabaseApiError(RuntimeError):
    pass


class SupabaseSqlClient:
    def __init__(self, access_token: str, project_ref: str, timeout: float = 60.0):
        self._client = httpx.Client(
            base_url=API_BASE,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )
        self._ref = project_ref

    def query(self, sql: str) -> list[dict]:
        response = self._client.post(
            f"/projects/{self._ref}/database/query",
            json={"query": sql},
        )
        if response.status_code not in (200, 201):  # 201 for DDL statements
            raise SupabaseApiError(f"query failed ({response.status_code}): {response.text[:400]}")
        return response.json() or []

    def close(self) -> None:
        self._client.close()


def apply_sql(client: SupabaseSqlClient, sql: str) -> None:
    """Execute a multi-statement script atomically."""
    client.query("BEGIN;\n" + sql + "\nCOMMIT;")
