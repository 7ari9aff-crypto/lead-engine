"""Outbound webhook delivery for v6 events — the integration layer.

For every org that registered an endpoint (events.webhook_endpoints), each
published event of a subscribed type is POSTed HMAC-signed:

    X-LeadEngine-Timestamp: <unix seconds>
    X-LeadEngine-Signature: hex(hmac_sha256(secret, "<ts>.<body>"))

Semantics: at-least-once. A raising consumer makes the OutboxRelay retry on
the next tick; consumers that register nothing deliver nothing (zero cost).

SSRF: endpoint URLs are resolved and rejected when they point at private
space (same discipline as the legacy netguard — duplicated here because the
v6 import boundary forbids reaching into the legacy package).
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
import socket
import time
import urllib.parse
from typing import Any

import httpx

from contracts.events import EventEnvelope

DELIVERED_TYPES = frozenset({
    "lead.ready_for_review", "lead.approved", "lead.rejected",
})
_TIMEOUT = 10.0


class UnsafeTarget(ValueError):
    pass


def _assert_public_host(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeTarget("only http(s) URLs are allowed")
    if parsed.username or parsed.password:
        raise UnsafeTarget("credentials in URL are not allowed")
    host = (parsed.hostname or "").lower()
    infos: list = []
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return  # unresolvable fails naturally at delivery time
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise UnsafeTarget(f"host {host} resolves to non-public address")


def sign(secret: str, timestamp: str, body: str) -> str:
    return hmac.new(secret.encode(), f"{timestamp}.{body}".encode(),
                    hashlib.sha256).hexdigest()


def build_payload(event: EventEnvelope, timestamp: str) -> str:
    import json

    return json.dumps({
        "event_id": event.event_id,
        "type": event.type,
        "version": event.version,
        "organization_id": event.org_id,
        "aggregate": {"type": event.aggregate_type, "id": event.aggregate_id},
        "payload": event.payload,
        "timestamp": timestamp,
    }, ensure_ascii=False, default=str)


class WebhookDispatchConsumer:
    """OutboxRelay consumer: delivers published events to registered
    org endpoints. Raises on hard failures so the relay retries."""

    def __init__(self, db, secret_key: bytes):
        self._db = db
        self._key = secret_key

    def _endpoints(self, org_id: str, event_type: str) -> list[dict[str, Any]]:
        with self._db.tx_system() as conn, conn.cursor() as cur:
            rows = cur.execute(
                """SELECT id::text, url, secret_enc, events
                   FROM events.webhook_endpoints
                   WHERE org_id = %s AND enabled""", (org_id,)).fetchall()
        out = []
        for r in rows or []:
            subscribed = r["events"] or ["*"]
            if "*" in subscribed or event_type in subscribed:
                out.append(r)
        return out

    def __call__(self, event: EventEnvelope) -> None:
        if event.type not in DELIVERED_TYPES or not event.org_id:
            return
        for endpoint in self._endpoints(self._db, event.org_id, event.type):
            self._deliver(event, endpoint)

    def _deliver(self, event: EventEnvelope, endpoint: dict[str, Any]) -> None:
        secret = _decrypt_secret(self._key, str(endpoint["secret_enc"]))
        timestamp = str(int(time.time()))
        body = build_payload(event, timestamp)
        _assert_public_host(endpoint["url"])
        resp = httpx.post(
            endpoint["url"],
            content=body.encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-LeadEngine-Timestamp": timestamp,
                "X-LeadEngine-Signature": f"v1={sign(secret, timestamp, body)}",
            },
            timeout=_TIMEOUT)
        if resp.status_code >= 400:
            raise RuntimeError(
                f"webhook {endpoint['id'][:8]} responded {resp.status_code}")


def _decrypt_secret(key: bytes, blob: str) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    raw = bytes.fromhex(blob)
    nonce, ct = raw[:12], raw[12:]
    return AESGCM(key).decrypt(nonce, ct, None).decode("utf-8")


def encrypt_secret(key: bytes, plain: str) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, plain.encode("utf-8"), None)
    return (nonce + ct).hex()
