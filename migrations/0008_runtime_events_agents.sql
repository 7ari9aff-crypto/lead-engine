-- 0008: Runtime plane — durable jobs, outbox, inbox, dead letters, effect
-- ledger. These are SYSTEM tables: cross-tenant by design (workers, relay,
-- consumers), so RLS is intentionally not applied here; tenant scoping for
-- business truth lives in the tenant-owned schemas (0001..0007).

CREATE SCHEMA IF NOT EXISTS runtime;
CREATE SCHEMA IF NOT EXISTS events;
CREATE SCHEMA IF NOT EXISTS effects;
CREATE SCHEMA IF NOT EXISTS agents;

CREATE TABLE runtime.jobs (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id              uuid NOT NULL,
  campaign_id         uuid,
  job_type            text NOT NULL,
  queue               text NOT NULL DEFAULT 'default',
  state               text NOT NULL DEFAULT 'QUEUED'
                      CHECK (state IN ('CREATED','QUEUED','PLANNING','DISCOVERING','RESEARCHING',
                                       'ENRICHING','VERIFYING','SCORING','QUALIFYING',
                                       'READY_FOR_REVIEW','WAITING_FOR_CAPACITY','WAITING_FOR_USER',
                                       'PAUSED','CANCELLING','CANCELLED','FAILED','PARTIAL_SUCCESS')),
  payload             jsonb NOT NULL DEFAULT '{}'::jsonb,
  checkpoint          jsonb NOT NULL DEFAULT '{}'::jsonb,
  current_phase       text,
  attempts            int NOT NULL DEFAULT 0,
  max_attempts        int NOT NULL DEFAULT 3,
  priority            int NOT NULL DEFAULT 100,
  lease_token         uuid,
  lease_version       bigint NOT NULL DEFAULT 0,
  lease_expires_at    timestamptz,
  cancel_requested_at timestamptz,
  cancelled_by        text,
  cancellation_reason text,
  last_error          text,
  worker_id           text,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  started_at          timestamptz,
  finished_at         timestamptz
);
CREATE INDEX idx_jobs_claim ON runtime.jobs (queue, state, priority, created_at)
  WHERE state IN ('QUEUED','CANCELLING');
CREATE INDEX idx_jobs_lease ON runtime.jobs (lease_expires_at)
  WHERE state IN ('PLANNING','DISCOVERING','RESEARCHING','ENRICHING','VERIFYING','SCORING','QUALIFYING','CANCELLING');
CREATE INDEX idx_jobs_org ON runtime.jobs (org_id, created_at DESC);

CREATE TABLE runtime.job_events (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  job_id      uuid NOT NULL REFERENCES runtime.jobs(id),
  org_id      uuid NOT NULL,
  kind        text NOT NULL,
  data        jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_job_events_job ON runtime.job_events (job_id, id);

-- Outbox: authoritative event record. Written in the SAME transaction as the
-- business mutation it describes.
CREATE TABLE events.outbox (
  event_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  version         int NOT NULL DEFAULT 1,
  type            text NOT NULL,
  aggregate_type  text NOT NULL,
  aggregate_id    text NOT NULL,
  org_id          uuid NOT NULL,
  producer        text NOT NULL,
  trace_id        text,
  correlation_id  text,
  causation_id    text,
  payload         jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at      timestamptz NOT NULL DEFAULT now(),
  published_at    timestamptz,
  publish_attempts int NOT NULL DEFAULT 0
);
CREATE INDEX idx_outbox_pending ON events.outbox (created_at)
  WHERE published_at IS NULL;

-- Inbox: idempotent consumption. Duplicate deliveries are skipped.
CREATE TABLE events.event_consumptions (
  consumer     text NOT NULL,
  event_id     uuid NOT NULL REFERENCES events.outbox(event_id),
  consumed_at  timestamptz NOT NULL DEFAULT now(),
  result       text NOT NULL DEFAULT 'ok',
  PRIMARY KEY (consumer, event_id)
);

CREATE TABLE events.dead_letters (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  consumer     text NOT NULL,
  event_id     uuid NOT NULL,
  event_type   text NOT NULL,
  payload      jsonb NOT NULL,
  error        text NOT NULL,
  attempts     int NOT NULL DEFAULT 1,
  created_at   timestamptz NOT NULL DEFAULT now()
);

-- Effect ledger: every external side effect is recorded with a deterministic
-- idempotency key BEFORE it happens; providers without idempotency support
-- get reconciliation instead of blind retries.
CREATE TABLE effects.effect_ledger (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id            uuid NOT NULL,
  job_id            uuid,
  step_id           uuid,
  provider_id       text NOT NULL,
  operation         text NOT NULL,
  idempotency_key   text NOT NULL UNIQUE,
  request_hash      text NOT NULL,
  status            text NOT NULL DEFAULT 'reserved'
                    CHECK (status IN ('reserved','succeeded','failed','uncertain')),
  result_digest     text,
  cost_cents        numeric NOT NULL DEFAULT 0,
  reconciled_at     timestamptz,
  created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_effects_job ON effects.effect_ledger (job_id);
CREATE INDEX idx_effects_uncertain ON effects.effect_ledger (created_at)
  WHERE status = 'uncertain';

-- Agent runtime context: the agent proposes; it never owns business truth.
CREATE TABLE agents.agent_runs (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id       uuid NOT NULL,
  agent_type   text NOT NULL,
  agent_version text NOT NULL,
  state        text NOT NULL DEFAULT 'RUNNING'
               CHECK (state IN ('RUNNING','SUCCEEDED','FAILED','CANCELLED')),
  objective    text,
  budget       jsonb NOT NULL DEFAULT '{}'::jsonb,
  started_at   timestamptz NOT NULL DEFAULT now(),
  finished_at  timestamptz
);

CREATE TABLE agents.agent_steps (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id      uuid NOT NULL REFERENCES agents.agent_runs(id),
  seq         int NOT NULL,
  kind        text NOT NULL,
  input       jsonb NOT NULL DEFAULT '{}'::jsonb,
  output      jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (run_id, seq)
);

CREATE TABLE agents.tool_calls (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id       uuid NOT NULL REFERENCES agents.agent_runs(id),
  tool_id      text NOT NULL,
  tool_version text NOT NULL,
  input        jsonb NOT NULL DEFAULT '{}'::jsonb,
  output       jsonb NOT NULL DEFAULT '{}'::jsonb,
  risk_level   text NOT NULL DEFAULT 'low',
  effect_id    uuid REFERENCES effects.effect_ledger(id),
  created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE agents.approvals (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id        uuid NOT NULL,
  run_id        uuid REFERENCES agents.agent_runs(id),
  subject_type  text NOT NULL,
  subject_id    text NOT NULL,
  action        text NOT NULL,
  status        text NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','approved','rejected')),
  requested_by  text NOT NULL DEFAULT 'agent',
  decided_by    text,
  decided_at    timestamptz,
  reason        text,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_approvals_pending ON agents.approvals (org_id, status)
  WHERE status = 'pending';
