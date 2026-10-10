"""Webhook delivery: signature, payload shape, SSRF guard, endpoint filter."""
from __future__ import annotations

import uuid

import pytest

from contracts.events import EventEnvelope
from infrastructure.events.webhook_consumer import (
    UnsafeTarget, WebhookDispatchConsumer, build_payload, encrypt_secret, sign,
)

KEY = b"0" * 32


def _envelope(event_type: str = "lead.approved", org: str = "11111111-1111-1111-1111-111111111111"):
    return EventEnvelope(
        type=event_type, aggregate_type="lead",
        aggregate_id=str(uuid.uuid4()), org_id=org,
        payload={"score": 91},
    )


def test_signature_is_deterministic_hmac():
    import hashlib, hmac as hmac_mod
    body = build_payload(_envelope(), "1700000000")
    expected = hmac_mod.new(KEY, b"1700000000." + body.encode(),
                            hashlib.sha256).hexdigest()
    assert sign("k", "1700000000", body) == sign("k", "1700000000", body)
    assert sign(KEY.decode(), "1700000000", body) == expected


def test_payload_shape():
    import json
    env = _envelope()
    body = json.loads(build_payload(env, "1700000000"))
    assert body["event_id"] == env.event_id
    assert body["type"] == "lead.approved"
    assert body["payload"] == {"score": 91}


def test_non_deliverable_types_are_skipped():
    delivered = []
    consumer = WebhookDispatchConsumer(db=None, secret_key=KEY)

    class _NoQuery:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def cursor(self):
            raise AssertionError("must not query the database")

    consumer._db = type("DB", (), {"tx_system": lambda self: _NoQuery()})()
    consumer(_envelope("icp.created"))  # not in DELIVERED_TYPES — no DB touch
    consumer(_envelope("lead.approved", org=""))  # no org — no DB touch


def test_ssrf_guard_rejects_private_targets():
    from urllib.parse import urlparse
    import socket
    for url in ("http://127.0.0.1:9000/hook", "http://192.168.1.5/hook",
                "http://10.0.0.1/hook", "file:///etc/passwd"):
        with pytest.raises(UnsafeTarget):
            consumer = WebhookDispatchConsumer(db=None, secret_key=KEY)
            # the guard lives inside _deliver via _assert_public_host — call it directly
            from infrastructure.events.webhook_consumer import _assert_public_host
            _assert_public_host(url)


def test_encrypt_secret_roundtrip():
    blob = encrypt_secret(KEY, "whsec_abc123")
    from infrastructure.events.webhook_consumer import _decrypt_secret
    assert _decrypt_secret(KEY, blob) == "whsec_abc123"
