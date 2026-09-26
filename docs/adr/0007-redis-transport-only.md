# ADR-0007 — Redis is transport, not truth (deferred stream wiring)

Status: accepted

Redis 7 runs in the dev stack, but V6 phase 1 uses the Postgres-polling relay
(ADR-0005) as the event transport — the system runs correctly without Redis.
Redis Streams may be added as a transport adapter; because the outbox remains
authoritative and consumers are idempotent, adding/changing the transport
never touches domain code. Rate limiting and ephemeral locks may use Redis.
Nothing durable is ever stored only in Redis.
