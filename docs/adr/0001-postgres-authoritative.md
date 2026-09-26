# ADR-0001 — PostgreSQL is the only authoritative store

Status: accepted (locked invariant, supersedes the legacy dual-path)

## Context

The legacy system ran SQLite and Postgres side by side with schema drift and an
ephemeral SQLite production path. Lead Engine V6 declares PostgreSQL as the
authoritative source of truth for business state, job state, outbox, audit,
idempotency, lineage, policy decisions and usage records.

## Decision

- The V6 stack talks to PostgreSQL only. No SQLite code path exists in V6.
- Supabase managed Postgres is the initial provider (ADR-0002).
- Local dev and tests run against Postgres 16 via `docker-compose.v6.yml`.
- All schema changes go through `migrations/` applied by `python -m apps.cli migrate`.
  Runtime DDL (`CREATE TABLE` at startup, DDL during requests) is forbidden.

## Consequences

- The legacy `lead_engine` stack keeps running until each of its duties is
  strangled; V6 code never falls back to SQLite.
