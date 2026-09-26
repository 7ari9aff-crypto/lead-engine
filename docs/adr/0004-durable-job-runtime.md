# ADR-0004 — Durable job runtime: leases, fencing, checkpoints

Status: accepted (implements locked invariants)

- Jobs live in `runtime.jobs` with the V6 lifecycle
  (CREATED → QUEUED → …phases… → READY_FOR_REVIEW + side states).
- A worker claims a job with `SELECT … FOR UPDATE SKIP LOCKED`, stamping
  `lease_token` (fresh uuid), incrementing `lease_version`, setting
  `lease_expires_at`.
- Heartbeat renews `lease_expires_at` during long phases.
- **Every sensitive write is fenced**: `WHERE lease_token = :token AND
  lease_version = :version`. A stale writer gets 0 rows → `LeaseLostError` →
  the worker stops touching the job.
- A reaper requeues jobs whose lease expired. Execution is at-least-once;
  handlers must therefore be idempotent (effect ledger + claim truth rules).
- Checkpoints (JSONB) are saved at every phase boundary and every N tool calls;
  a resumed job continues from its last checkpoint, never from RAM state.
- Cancellation is a state machine: RUNNING → CANCELLING (compensation/
  reconciliation) → CANCELLED, checked between phases, tool calls and after
  provider calls.
