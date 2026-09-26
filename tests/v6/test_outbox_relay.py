"""Outbox relay + idempotent consumer semantics (ADR-0005)."""
from __future__ import annotations

from uuid import uuid4

from contracts.events import EventEnvelope, serialize
from infrastructure.events.relay import IdempotentConsumer, OutboxRelay
from psycopg.types.json import Json


def _emit(db, org: str, type_: str = "test.event", payload: dict | None = None) -> str:
    event = EventEnvelope(type=type_, aggregate_type="test", aggregate_id=uuid4().hex,
                          org_id=org, payload=payload or {"n": 1})
    with db.tx_system() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO events.outbox (event_id, type, aggregate_type, aggregate_id,
                                         org_id, producer, payload)
               VALUES (%s, %s, %s, %s, %s, 'test', %s) RETURNING event_id""",
            (event.event_id, event.type, event.aggregate_type, event.aggregate_id,
             event.org_id, Json(serialize(event.payload))),
        )
        return str(cur.fetchone()["event_id"])


def test_relay_delivers_once_and_marks_published(db, org):
    seen: list[str] = []
    relay = OutboxRelay(db, consumer=lambda e: seen.append(e.event_id))
    event_id = _emit(db, org)

    assert relay.tick() == 1
    assert seen == [event_id]
    assert relay.tick() == 0          # published — no redelivery
    with db.tx_system() as conn, conn.cursor() as cur:
        row = cur.execute("SELECT published_at FROM events.outbox WHERE event_id = %s",
                          (event_id,)).fetchone()
    assert row["published_at"] is not None


def test_consumer_dedups_duplicate_deliveries(db, org):
    seen: list[str] = []
    consumer = IdempotentConsumer(db, "test-consumer", lambda e: seen.append(e.event_id))
    relay = OutboxRelay(db, consumer=consumer)
    event_id = _emit(db, org)

    relay.tick()
    # simulate at-least-once redelivery: unmark published, tick again
    with db.tx_system() as conn, conn.cursor() as cur:
        cur.execute("UPDATE events.outbox SET published_at = NULL WHERE event_id = %s",
                    (event_id,))
    relay.tick()
    assert seen.count(event_id) == 1  # duplicate skipped by the inbox


def test_poison_event_retries_then_dead_letters(db, org):
    attempts = {"n": 0}

    def always_fails(event):
        attempts["n"] += 1
        raise RuntimeError("poison")

    consumer = IdempotentConsumer(db, "poison-consumer", always_fails, max_attempts=3)
    relay = OutboxRelay(db, consumer=consumer)
    event_id = _emit(db, org)

    for _ in range(5):
        with db.tx_system() as conn, conn.cursor() as cur:
            cur.execute("UPDATE events.outbox SET published_at = NULL WHERE event_id = %s",
                        (event_id,))
        relay.tick()

    assert attempts["n"] == 3  # exactly max_attempts executions
    with db.tx_system() as conn, conn.cursor() as cur:
        dead = cur.execute("SELECT * FROM events.dead_letters WHERE event_id = %s",
                           (event_id,)).fetchone()
        inbox = cur.execute(
            "SELECT result FROM events.event_consumptions WHERE consumer='poison-consumer'"
            " AND event_id = %s", (event_id,)).fetchone()
    assert dead is not None and "poison" in dead["error"]
    assert inbox["result"] == "dead-lettered"
