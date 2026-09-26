"""Outbox relay (polling, at-least-once) and idempotent consumer toolkit.

Delivery semantics:
- relay_tick: fetch unpublished events (FOR UPDATE SKIP LOCKED), hand each to
  the consumer, mark published. A crash between dispatch and mark re-delivers.
- IdempotentConsumer: first delivery records the inbox row and runs the
  handler. On failure the inbox row is deleted so the next relay tick retries;
  after max_attempts failures the event is parked in events.dead_letters and
  the inbox row is re-recorded with result='dead-lettered' to stop the loop.
"""
from __future__ import annotations

import json
from typing import Any, Callable

from contracts.events import EventEnvelope


def _to_envelope(row: dict[str, Any]) -> EventEnvelope:
    return EventEnvelope(
        type=row["type"],
        aggregate_type=row["aggregate_type"],
        aggregate_id=row["aggregate_id"],
        org_id=str(row["org_id"]),
        payload=row["payload"] or {},
        version=row["version"],
        producer=row["producer"],
        event_id=str(row["event_id"]),
        trace_id=row["trace_id"],
        correlation_id=row["correlation_id"],
        causation_id=row["causation_id"],
    )


class OutboxRelay:
    def __init__(self, db, consumer: Callable[[EventEnvelope], None], batch_size: int = 100):
        self._db = db
        self._consumer = consumer
        self._batch = batch_size

    def tick(self) -> int:
        """One relay pass. Returns the number of events dispatched."""
        with self._db.tx_system() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT * FROM events.outbox
                   WHERE published_at IS NULL
                   ORDER BY created_at
                   LIMIT %s
                   FOR UPDATE SKIP LOCKED""",
                (self._batch,),
            )
            rows = cur.fetchall()
            if not rows:
                return 0

        dispatched = 0
        for row in rows:
            event = _to_envelope(row)
            # count the attempt BEFORE dispatch so the consumer can DLQ on the
            # exact max_attempts-th failure
            with self._db.tx_system() as conn, conn.cursor() as cur:
                cur.execute(
                    "UPDATE events.outbox SET publish_attempts = publish_attempts + 1"
                    " WHERE event_id = %s",
                    (row["event_id"],),
                )
            try:
                self._consumer(event)
            except Exception:
                continue  # retry on a later tick (consumer handles DLQ)
            with self._db.tx_system() as conn, conn.cursor() as cur:
                cur.execute(
                    "UPDATE events.outbox SET published_at = now()"
                    " WHERE event_id = %s AND published_at IS NULL",
                    (row["event_id"],),
                )
            dispatched += 1
        return dispatched


class IdempotentConsumer:
    """Inbox dedup + retry via redelivery + DLQ after max_attempts."""

    def __init__(self, db, consumer_name: str, handler: Callable[[EventEnvelope], None],
                 max_attempts: int = 3):
        self._db = db
        self._name = consumer_name
        self._handler = handler
        self._max = max_attempts

    def __call__(self, event: EventEnvelope) -> None:
        with self._db.tx_system() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT result FROM events.event_consumptions
                   WHERE consumer = %s AND event_id = %s""",
                (self._name, event.event_id),
            )
            existing = cur.fetchone()
        if existing is not None:
            return  # already processed (or dead-lettered)

        try:
            self._handler(event)
        except Exception as exc:  # noqa: BLE001
            self._on_failure(event, str(exc))
            raise

        with self._db.tx_system() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO events.event_consumptions (consumer, event_id, result)
                   VALUES (%s, %s, 'ok')""",
                (self._name, event.event_id),
            )

    def _on_failure(self, event: EventEnvelope, error: str) -> None:
        """Delete the inbox claim so redelivery can retry; DLQ after max."""
        with self._db.tx_system() as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM events.event_consumptions WHERE consumer = %s AND event_id = %s",
                (self._name, event.event_id),
            )
            attempts = cur.execute(
                """SELECT publish_attempts FROM events.outbox WHERE event_id = %s""",
                (event.event_id,),
            ).fetchone()["publish_attempts"]
            if attempts >= self._max:
                cur.execute(
                    """INSERT INTO events.dead_letters
                         (consumer, event_id, event_type, payload, error, attempts)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (self._name, event.event_id, event.type,
                     json.dumps(event.payload, default=str), error, attempts),
                )
                cur.execute(
                    """INSERT INTO events.event_consumptions (consumer, event_id, result)
                       VALUES (%s, %s, 'dead-lettered')""",
                    (self._name, event.event_id),
                )
