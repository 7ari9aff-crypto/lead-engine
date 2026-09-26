# Lead Engine V6 — Operations Quickstart

Branch `v6-foundation`. The legacy stack keeps running untouched on `main`;
V6 supersedes it boundary by boundary (ADR-0001..0009 in `docs/adr/`).

## One-time setup

```bash
# in .env (already present on this machine):
# SUPABASE_DB_URL=...                     # Supabase direct connection
# LEAD_ENGINE_V6_SUPABASE_ACCESS_TOKEN=…  # Management API (migrations run as postgres)
# SUPABASE_PROJECT_REF=…

python -m apps.cli migrate      # applies migrations/*.sql (the ONLY schema path)
```

## Run the stack (two processes — that is the architecture)

```bash
# terminal 1 — API
python -m apps.api --port 8002

# terminal 2 — worker (one binary, queue subscriptions)
LEAD_ENGINE_V6_DEMO=1 python -m apps.worker --queues default

# LEAD_ENGINE_V6_DEMO=1 wires deterministic demo providers; production
# adapters slot into the same gateway contract later (ADR-0009).
```

## Live journey (curl)

```bash
SVC="Authorization: Bearer $V6_SERVICE_TOKEN"

# 1. tenant bootstrap
curl -X POST :8002/api/v1/platform/onboard -H "$SVC" -H "Content-Type: application/json" \
  -d '{"slug":"demo","name":"Demo","plan_code":"pro","owner_ext_id":"owner-1"}'

# 2. campaign (ICP versioned immutable + job enqueued, entitlements pre-checked)
curl -X POST :8002/api/v1/campaigns -H "$SVC" -H "X-Org-Id: $ORG" \
  -H "Content-Type: application/json" -d '{"name":"Riyadh","icp":{…}}'

# 3. a worker process picks it up; poll until READY_FOR_REVIEW
curl :8002/api/v1/jobs/$JOB -H "$SVC" -H "X-Org-Id: $ORG"

# 4. human review boundary
curl :8002/api/v1/review/pending -H "$SVC" -H "X-Org-Id: $ORG"
curl -X POST :8002/api/v1/review/leads/$LEAD/decision -H "$SVC" -H "X-Org-Id: $ORG" \
  -d '{"approve": true}'

# 5. purpose-bound PII (plaintext only for APPROVED leads; every access audited)
curl -X POST :8002/api/v1/leads/$LEAD/pii -H "$SVC" -H "X-Org-Id: $ORG" \
  -d '{"purpose": "outreach"}'

# 6. business lineage — "why is this lead here?"
curl :8002/api/v1/lineage/leads/$LEAD -H "$SVC" -H "X-Org-Id: $ORG"
```

## Tests

```bash
python -m pytest tests/v6 -q    # 40 tests: boundaries, domain, runtime fencing,
                                # relay/DLQ, RLS isolation, vault audit, E2E, API
```

## What is intentionally NOT here yet

- Real provider adapters in `infrastructure/providers/` (fakes carry the same
  contract; wiring keys is additive).
- Frontend modules against the typed client (the legacy dashboard keeps
  working; V6 client generation is the next wave).
- Outreach/revenue-execution plugin (the boundary exists: APPROVED leads +
  purpose-gated PII; nothing sends anything yet, by design).
