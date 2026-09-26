# ADR-0005 — Transactional outbox with polling relay and idempotent inbox

Status: accepted (implements locked invariants)

- Business mutation + `events.outbox` insert + idempotency record commit
  atomically in one transaction.
- The relay is a DB-polling dispatcher (at-least-once). Redis Streams can wrap
  the same contract later (ADR-0007) without changing event semantics.
- Consumers record deliveries in `events.event_consumptions (consumer,
  event_id)`; duplicates are skipped. Poison events go to
  `events.dead_letters` after N attempts, with audit.
- Events carry the full envelope (§32 of the architecture): event_id, version,
  type, aggregate, tenant, producer, trace/correlation/causation ids, payload.
  Plaintext PII inside events is forbidden.
