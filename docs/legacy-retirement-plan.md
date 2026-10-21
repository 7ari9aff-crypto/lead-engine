# Legacy retirement plan (SQLite / `engine.*` / `public.*` -> V6)

Status: **proposal, no code or data changed.** Measured against production on 2026-10-21.

## Why not "just stop it"

| Signal | Legacy | V6 |
|---|---|---|
| Last activity | today 06:38 UTC | today 09:07 UTC |
| Driven by `worker-tick` (every 5 min) | yes (`lead_engine.worker`) | no |
| Leads | `engine.leads` 121, `public.leads` 126 | `projects.lead_projections` 3 |
| Jobs | 38 (1 QUEUED now) | 15 `acquisition.run` (13 PARTIAL_SUCCESS) |

Stopping legacy today would stop lead production. V6 also imports `lead_engine`
for auth, `open_db` and secret hydration (`v6api/bridge.py`,
`apps/api/__main__.py`, `apps/worker/__main__.py`).

Data volume is small (about 2,000 legacy rows), so migration is cheap and the
risk is behavioural, not volume.

## Phases (each is its own PR, CI green, reversible)

1. **Parity first.** Find why 13/14 V6 jobs end `PARTIAL_SUCCESS` and why
   projections are 3 vs 121 leads. Add a parity test: same ICP input, legacy and
   V6 produce equivalent leads.
2. **Shadow run.** Keep legacy as the source of truth, run V6 on the same jobs,
   diff results daily (read-only). Exit criterion: 2 weeks with no material diff.
3. **Move the invariants.** Port the pieces V6 borrows from legacy
   (auth claims, DB open, secret hydration) into V6 modules, so V6 no longer
   imports `lead_engine`.
4. **Backfill.** Copy `engine.leads` / `public.leads` / evidence into V6 tables
   with a dry-run report first (counts + checksums per org). Erased rows
   (`legal_decision = 'retention-erased'`, 28 ACCEPTED ones today) must stay
   erased and must NOT be re-materialised.
5. **Cut over reads, then writes.** Flip `worker-tick` to the V6 worker; keep
   legacy tables read-only.
6. **Retire.** Only after the owner explicitly approves: archive (pg_dump to
   cold storage, verified restore), then drop. **Nothing is deleted before that
   approval.**

## Rollback
Every phase before 6 is a config/code flip; legacy tables stay intact and
writable until the last step.
