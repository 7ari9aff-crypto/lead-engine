"""Composition: register all sentinel checks + the worker alert writer."""
from __future__ import annotations

import json

from psycopg.types.json import Json

from application.doctor.doctor import Doctor
from application.doctor.checks import (
    check_app_role,
    check_db_latency,
    check_dead_letters,
    check_failing_jobs,
    check_http_surface,
    check_migrations,
    check_models,
    check_orphaned_jobs,
    check_outbox_stall,
    check_pii_plaintext,
    check_provider_health,
    check_queue_starved,
    check_rls_enforced,
    check_schedule_stalled,
    check_stale_alerts_open,
    check_stale_approvals,
    check_stuck_jobs,
    check_verification_quality,
    check_uncertain_effects,
    check_vault_roundtrip,
    check_workers_alive,
    check_zero_candidate_runs,
)


def build_doctor(backend, vault=None, gateway=None, model_gateway=None) -> Doctor:
    doctor = Doctor(backend)
    doctor.register("db.latency", check_db_latency)
    doctor.register("db.migrations", check_migrations)
    doctor.register("db.rls", check_rls_enforced)
    doctor.register("db.app_role", check_app_role)
    doctor.register("queue.starved", check_queue_starved)
    doctor.register("queue.stuck", check_stuck_jobs)
    doctor.register("queue.orphaned", check_orphaned_jobs)
    doctor.register("verify.quality", lambda b, sc, org: check_verification_quality(b, sc, org))
    doctor.register("jobs.failing", check_failing_jobs)
    doctor.register("events.outbox", check_outbox_stall)
    doctor.register("events.dead_letters", check_dead_letters)
    doctor.register("effects.uncertain", check_uncertain_effects)
    doctor.register("honesty.zero_candidates", check_zero_candidate_runs)
    doctor.register("schedule.stalled", check_schedule_stalled)
    doctor.register("http.surface", lambda b, sc, org: check_http_surface(b, sc, org))
    doctor.register("pii.plaintext", check_pii_plaintext)
    doctor.register("workers.alive", check_workers_alive)
    doctor.register("agent.approvals_stale", check_stale_approvals)
    doctor.register("sentinel.open_alerts", check_stale_alerts_open)

    # checks needing composition objects
    doctor.register("pii.vault", lambda b, s, org: check_vault_roundtrip(b, s, org, vault))
    doctor.register("providers.health", lambda b, s, org: check_provider_health(b, s, org, gateway))
    doctor.register("models.gateway", lambda b, s, org: check_models(b, s, org, model_gateway))
    return doctor


def write_alerts(db, report) -> dict[str, int]:
    """Persist FAIL/WARN findings as durable alerts; auto-resolve checks that
    returned to OK. Returns {opened, resolved}."""
    opened = resolved = 0
    with db.tx_system() as conn, conn.cursor() as cur:
        for check in report.checks:
            if check.status in ("WARN", "FAIL"):
                cur.execute(
                    """SELECT id::text FROM runtime.alerts
                       WHERE check_id = %s AND resolved_at IS NULL LIMIT 1""",
                    (check.check_id,))
                existing = cur.fetchone()
                if existing:
                    cur.execute(
                        """UPDATE runtime.alerts
                           SET status = %s, cause = %s, evidence = %s
                           WHERE id = %s AND resolved_at IS NULL""",
                        (check.status, check.cause,
                         Json(json.dumps(check.evidence, default=str)),
                         existing["id"]))
                else:
                    cur.execute(
                        """INSERT INTO runtime.alerts (check_id, status, cause, evidence)
                           VALUES (%s, %s, %s, %s)""",
                        (check.check_id, check.status, check.cause,
                         Json(json.dumps(check.evidence, default=str))))
                    opened += 1
            elif check.status == "OK":
                cur.execute(
                    """UPDATE runtime.alerts SET resolved_at = now()
                       WHERE check_id = %s AND resolved_at IS NULL""",
                    (check.check_id,))
                resolved += cur.rowcount
    return {"opened": opened, "resolved": resolved}


def write_heartbeat(db, worker_id: str, queues: str) -> None:
    with db.tx_system() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO runtime.worker_heartbeats (worker_id, queues, last_beat)
               VALUES (%s, %s, now())
               ON CONFLICT (worker_id) DO UPDATE
                 SET queues = EXCLUDED.queues, last_beat = now()""",
            (worker_id, queues))
