-- 0012: Sentinel tables — durable alerts (open until resolved) and worker
-- heartbeats (worker liveness). The doctor reads and writes these; the
-- worker's maintenance loop writes heartbeats and opens/resolves alerts.

CREATE TABLE IF NOT EXISTS runtime.alerts (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  check_id    text NOT NULL,
  status      text NOT NULL CHECK (status IN ('WARN','FAIL')),
  cause       text NOT NULL,
  evidence    jsonb NOT NULL DEFAULT '{}'::jsonb,
  opened_at   timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz
);
CREATE INDEX idx_alerts_open ON runtime.alerts (check_id, opened_at DESC)
  WHERE resolved_at IS NULL;

CREATE TABLE IF NOT EXISTS runtime.worker_heartbeats (
  worker_id  text PRIMARY KEY,
  queues     text NOT NULL DEFAULT '',
  last_beat  timestamptz NOT NULL DEFAULT now()
);
