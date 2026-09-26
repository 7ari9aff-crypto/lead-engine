"""Durable runtime tests: claim, fencing, heartbeat, cancellation, reaper.

Each test uses its OWN queue so global claim never grabs another test's job.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from contracts.errors import LeaseLostError
from runtime import leasing


def _queue() -> str:
    return f"q-{uuid4().hex[:10]}"


def test_claim_and_fenced_checkpoint(db, org):
    q = _queue()
    job_id = leasing.create_job(db, org, "acquisition.run", {}, queue=q)
    job = leasing.claim_next(db, [q], "w1", lease_seconds=120)
    assert job is not None and str(job["org_id"]) == org

    token = str(job["lease_token"])
    version = int(job["lease_version"])

    leasing.save_checkpoint(db, job_id, token, version, {"i": 1}, state="DISCOVERING")
    row = leasing.get_job(db, org, job_id)
    assert row["checkpoint"]["i"] == 1 and row["state"] == "DISCOVERING"

    with pytest.raises(LeaseLostError):
        leasing.save_checkpoint(db, job_id, token, version - 1, {"i": 2})

    with pytest.raises((LeaseLostError, ValueError)):
        leasing.save_checkpoint(db, job_id, "0" * 32, version, {"i": 3})


def test_complete_is_fenced_and_invalidates_lease(db, org):
    q = _queue()
    job_id = leasing.create_job(db, org, "acquisition.run", {}, queue=q)
    job = leasing.claim_next(db, [q], "w1", 120)
    leasing.complete(db, job_id, str(job["lease_token"]), int(job["lease_version"]))
    assert leasing.get_job(db, org, job_id)["state"] == "READY_FOR_REVIEW"
    with pytest.raises(LeaseLostError):
        leasing.complete(db, job_id, str(job["lease_token"]), int(job["lease_version"]))


def test_failure_requeues_until_max_attempts(db, org):
    q = _queue()
    job_id = leasing.create_job(db, org, "acquisition.run", {}, queue=q, max_attempts=2)
    state = None
    for _ in range(2):
        job = leasing.claim_next(db, [q], "w1", 120)
        state = leasing.fail(db, job_id, str(job["lease_token"]),
                             int(job["lease_version"]), "boom")
    assert state == "FAILED"
    row = leasing.get_job(db, org, job_id)
    assert row["state"] == "FAILED" and row["attempts"] == 2 and "boom" in row["last_error"]


def test_heartbeat_renews_and_fences(db, org):
    q = _queue()
    job_id = leasing.create_job(db, org, "acquisition.run", {}, queue=q)
    leasing.claim_next(db, [q], "w1", 1)
    job = leasing.get_job(db, org, job_id)
    assert leasing.heartbeat(db, job_id, str(job["lease_token"]), 300) is True
    assert leasing.heartbeat(db, job_id, "not-a-uuid", 300) is False


def test_reaper_requeues_expired_leases(db, org):
    q = _queue()
    job_id = leasing.create_job(db, org, "acquisition.run", {}, queue=q)
    job = leasing.claim_next(db, [q], "w1", 120)
    token, version = str(job["lease_token"]), int(job["lease_version"])
    leasing.set_phase(db, job_id, token, version, "DISCOVERING")

    with db.tx_system() as conn, conn.cursor() as cur:
        cur.execute("UPDATE runtime.jobs SET lease_expires_at = now() - interval '1s'"
                    " WHERE id = %s", (job_id,))
    requeued = leasing.reclaim_expired(db)
    assert job_id in requeued
    row = leasing.get_job(db, org, job_id)
    assert row["state"] == "QUEUED" and row["lease_token"] is None
    # the stale worker's fenced write now loses
    with pytest.raises(LeaseLostError):
        leasing.set_phase(db, job_id, token, version, "ENRICHING")


def test_cancellation_state_machine(db, org):
    q = _queue()
    job_id = leasing.create_job(db, org, "acquisition.run", {}, queue=q)
    job = leasing.claim_next(db, [q], "w1", 120)
    token, version = str(job["lease_token"]), int(job["lease_version"])

    assert leasing.request_cancel(db, org, job_id, "user-1", "not needed") is True
    assert leasing.apply_cancellation(db, job_id, token, version) is True
    assert leasing.get_job(db, org, job_id)["state"] == "CANCELLING"
    leasing.finish_cancelled(db, job_id, token, version)
    assert leasing.get_job(db, org, job_id)["state"] == "CANCELLED"


def test_two_workers_never_claim_the_same_job(db, org):
    q = _queue()
    job_id = leasing.create_job(db, org, "acquisition.run", {}, queue=q)
    first = leasing.claim_next(db, [q], "w1", 120)
    second = leasing.claim_next(db, [q], "w2", 120)
    assert str(first["id"]) == job_id
    assert second is None or str(second["id"]) != job_id
