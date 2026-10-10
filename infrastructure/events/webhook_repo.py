"""Webhook endpoint management — the org's outbound integration surface."""
from __future__ import annotations

from typing import Any

from infrastructure.events.webhook_consumer import encrypt_secret


class WebhookEndpointRepo:
    def __init__(self, cur):
        self.cur = cur

    def list(self) -> list[dict[str, Any]]:
        return list(cur_list(self.cur))

    def create(self, url: str, secret_plain: str, events: list[str]) -> dict[str, Any]:
        row = self.cur.execute(
            """INSERT INTO events.webhook_endpoints
                 (org_id, url, secret_enc, events)
               VALUES (current_setting('app.tenant_id', true)::uuid, %s, %s, %s)
               RETURNING id::text, url, events, enabled, created_at::text""",
            (url, encrypt_secret(_key(), secret_plain), events or ["*"]),
        ).fetchone()
        return dict(row)

    def disable(self, endpoint_id: str) -> bool:
        row = self.cur.execute(
            """UPDATE events.webhook_endpoints SET enabled = false
               WHERE id = %s
                 AND org_id = current_setting('app.tenant_id', true)::uuid
               RETURNING id::text""", (endpoint_id,)).fetchone()
        return row is not None


def cur_list(cur) -> list[dict[str, Any]]:
    return list(cur.execute(
        """SELECT id::text, url, events, enabled, created_at::text
           FROM events.webhook_endpoints
           WHERE org_id = current_setting('app.tenant_id', true)::uuid
           ORDER BY created_at""").fetchall())


def _key() -> bytes:
    # The signing secrets are encrypted with the deployment master key —
    # resolved lazily from settings to avoid import cycles.
    from infrastructure.config import Settings

    return Settings.load().master_key
