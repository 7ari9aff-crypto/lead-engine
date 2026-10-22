# ADR-0011 — Asynchronous Manus discovery stage

Status: accepted (extends ADR-0009, ADR-0010)

## Context

Manus is a research agent, not a search API. One task takes 3 to 5 minutes and
costs credits (about 3.2 per lead on `manus-1.6-lite`; 48 credits for 15
clinics). The search gateway runs inside an open Postgres transaction, so
registering Manus as a `search_companies` adapter would hold that transaction
for minutes. Measured quality (15 Jeddah clinics): 15/15 real websites, 87%
of phones and 64% of emails confirmed on the company's own site by the
automatic verifier.

## Decision

A separate stage, `MANUS`, runs inside `acquisition.run` **only** when the ICP
sets `discovery.engine: manus`. Everything else is unchanged.

1. **Never block, never hold a transaction.** Submitting, polling and fetching
   company sites happen outside any unit of work. A short unit of work is opened
   only to ingest verified companies, through the same `_ingest_result` path as
   search results (identity resolution, dedup, claims, PII vault).
2. **Park, don't fail.** While tasks run the stage calls `ops.park`. The job goes
   to `WAITING_FOR_CAPACITY`, keeps its checkpoint, and does **not** burn an
   attempt. The worker's maintenance tick wakes parked jobs at most once per 45 s.
   Only jobs parked through `park()` are woken (marker `parked:` in `last_error`).
3. **Never pay twice.** Task ids are written to the checkpoint immediately after
   submission; a restarted worker resumes polling instead of resubmitting.
4. **Credit-aware key choice.** Manus has no balance endpoint, so a `KeyLedger`
   tracks estimated credits from each task's `credit_usage`. It picks the key with
   the most credit, refuses any key that would drop under the floor (30), holds an
   estimate while a task runs, skips a rate-limited key, and retires a key that
   returns 401/403. The checkpoint stores balances by key *position*, never by value.
5. **Trust nothing Manus says.** A phone or email is stored only if it appears on
   the company's own website (`verify_company`). Unverified values are dropped,
   not kept as "probably right". An unreachable site verifies nothing.
6. **Sector-agnostic.** The brief is built from the ICP (industry, cities,
   keywords). No sector is hardcoded.
7. **Keys** come from the encrypted credential store as `MANUS_API_KEY`
   (comma-separated pool) and are hydrated by the worker like any other key. They
   are never in GitHub or Vercel.

## Failure behavior

- Manus requested but no key: the job FAILS with an explicit message.
- Every key at the floor before anything was submitted: the job FAILS loudly.
- A task that never finishes is abandoned after 25 minutes and reported.
- A failed task is still charged what it used.

## Consequences

- One more job phase and one more fenced runtime operation (`park`).
- Credit balances are estimates; the first real run calibrates them.
- Not built here: a chat selector to pick Manus per task, and per-lead cost
  reporting in the UI.
