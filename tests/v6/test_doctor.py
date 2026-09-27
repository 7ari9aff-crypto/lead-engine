"""Sentinel (doctor) tests — seeded faults must surface with precise causes."""
from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4


from application.doctor.doctor import Doctor
from contracts.doctor import CheckStatus
from infrastructure.doctor.registry import build_doctor, write_alerts, write_heartbeat


def _emit_old_event(db, org: str, minutes: int = 30) -> None:
    with db.tx_system() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO events.outbox (type, aggregate_type, aggregate_id,
                                         org_id, producer, payload, created_at)
               VALUES ('test.stale', 'test', %s, %s, 'test', '{}'::jsonb,
                       now() - make_interval(mins => %s))""",
            (uuid4().hex, org, minutes))


def _insert_dead_letter(db) -> None:
    with db.tx_system() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO events.dead_letters (consumer, event_id, event_type,
                                                payload, error)
               VALUES ('test', gen_random_uuid(), 'test.event', '{}', 'boom: root cause')""")


def _insert_expired_lease_job(db, org: str) -> str:
    with db.tx_system() as conn, conn.cursor() as cur:
        row = cur.execute(
            """INSERT INTO runtime.jobs (org_id, job_type, queue, state,
                                         lease_expires_at)
               VALUES (%s, 'acquisition.run', 'default', 'DISCOVERING',
                       now() - interval '1 minute')
               RETURNING id""",
            (org,)).fetchone()
        return str(row["id"])


def test_all_checks_run_and_report(db, settings, uows, vault, fake_gateway):
    from infrastructure.repos.doctor_repo import DoctorRepo

    gateway, _ = fake_gateway
    doctor = build_doctor(DoctorRepo(db, "migrations" and
                                     Path("migrations")),
                          vault=vault, gateway=gateway, model_gateway=None)
    report = doctor.run(settings, org=None)
    ids = {c.check_id for c in report.checks}
    assert "db.latency" in ids and "db.rls" in ids and "pii.plaintext" in ids
    # no check crashed (every check has a status in the known set)
    assert all(c.status in (CheckStatus.OK, CheckStatus.WARN, CheckStatus.FAIL)
               for c in report.checks)
    # healthy database: nothing FAILs
    assert report.failing() == [], [(c.check_id, c.cause) for c in report.failing()]


def test_stuck_job_detected_with_precise_cause(db, org, settings, uows, vault,
                                               fake_gateway):
    from infrastructure.repos.doctor_repo import DoctorRepo

    _insert_expired_lease_job(db, org)
    doctor = build_doctor(DoctorRepo(db, Path("migrations")),
                          vault=vault, gateway=fake_gateway, model_gateway=None)
    report = doctor.run(settings, org=org)
    stuck = [c for c in report.checks if c.check_id == "queue.stuck"]
    assert stuck and stuck[0].status == CheckStatus.FAIL
    assert "lease" in stuck[0].cause


def test_dead_letter_surfaces_with_root_cause(db, org, settings, uows, vault, fake_gateway):
    from infrastructure.repos.doctor_repo import DoctorRepo

    _insert_dead_letter(db)
    doctor = build_doctor(DoctorRepo(db, Path("migrations")),
                          vault=vault, gateway=fake_gateway, model_gateway=None)
    report = doctor.run(settings, org=org)
    dead = [c for c in report.checks if c.check_id == "events.dead_letters"]
    assert dead and dead[0].status == CheckStatus.FAIL
    assert "boom: root cause" in json.dumps(dead[0].evidence)


def test_outbox_stall_detected(db, org, settings, uows, vault, fake_gateway):
    from infrastructure.repos.doctor_repo import DoctorRepo

    _emit_old_event(db, org)
    doctor = build_doctor(DoctorRepo(db, Path("migrations")),
                          vault=vault, gateway=fake_gateway, model_gateway=None)
    report = doctor.run(settings, org=org)
    stall = [c for c in report.checks if c.check_id == "events.outbox"]
    assert stall and stall[0].status == CheckStatus.FAIL
    assert "relay" in stall[0].cause
    # cleanup: the stale event would otherwise leak into test_outbox_relay's
    # tick counts (shared DB, one session)
    with db.tx_system() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM events.outbox WHERE type = 'test.stale'")


def test_plaintext_pii_scan(db, org, settings, uows, vault, fake_gateway):
    from infrastructure.repos.doctor_repo import DoctorRepo

    # plant a lead projection whose display blob contains a raw email
    with uows(org) as tx:
        company_id = tx.repos.companies.create_company(
            str(uuid4()), "Leaky Co", "leaky.sa", None, None, None)
        tx.repos.projects.upsert_lead(
            campaign_id=None, company_id=company_id, contact_id=None,
            icp_version_id=None,
            display={"name": "Leaky", "contact": "raw@leak.sa"},
            masked_email=None, masked_phone=None, email_status=None,
            score=10, score_version="v1", decision="review")
    doctor = build_doctor(DoctorRepo(db, Path("migrations")),
                          vault=vault, gateway=fake_gateway, model_gateway=None)
    report = doctor.run(settings, org=org)
    leak = [c for c in report.checks if c.check_id == "pii.plaintext"]
    assert leak and leak[0].status == CheckStatus.FAIL
    assert leak[0].evidence["lead_ids"]


def test_crashing_check_becomes_fail(db, settings):
    """THE core sentinel promise: a check that explodes is reported as FAIL
    with the exception — never silent."""
    doctor = Doctor(backend=None)

    def boom(backend, settings, org):
        raise RuntimeError("sensor exploded")

    doctor.register("boom", boom)
    report = doctor.run(settings, org=None)
    check = report.checks[0]
    assert check.status == CheckStatus.FAIL
    assert "sensor exploded" in check.cause


def test_alerts_dedup_and_autoresolve(db, org, settings, uows, vault, fake_gateway):
    from infrastructure.repos.doctor_repo import DoctorRepo

    doctor = build_doctor(DoctorRepo(db, Path("migrations")),
                          vault=vault, gateway=fake_gateway, model_gateway=None)

    # force a FAIL by planting a dead letter, then remove it → alert resolves
    _insert_dead_letter(db)
    report = doctor.run(settings, org=org)
    stats = write_alerts(db, report)
    assert stats["opened"] >= 1

    with db.tx_system() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM events.dead_letters WHERE consumer = 'test'")
    report2 = doctor.run(settings, org=org)
    stats2 = write_alerts(db, report2)
    assert stats2["resolved"] >= 1

    with db.tx_system() as conn, conn.cursor() as cur:
        open_dead = cur.execute(
            """SELECT count(*) AS n FROM runtime.alerts
               WHERE check_id = 'events.dead_letters' AND resolved_at IS NULL"""
        ).fetchone()["n"]
    assert open_dead == 0  # the dead-letter alert specifically auto-resolved


def test_worker_heartbeat_liveness(db, settings):

    write_heartbeat(db, "hb-worker", "default")
    row = db.query(None, "SELECT worker_id, queues FROM runtime.worker_heartbeats")
    assert any(r["worker_id"] == "hb-worker" for r in row)
