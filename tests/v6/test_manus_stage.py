"""Manus discovery stage inside the real pipeline (Postgres, real worker).

Pins the behavior that costs money or trust if wrong:
* off unless the ICP asks for it AND keys exist (existing runs are untouched);
* a slow task parks the job WITHOUT burning an attempt, then resumes;
* a restart never pays for the same task twice;
* only contacts confirmed on the company's own site are stored.
"""
from __future__ import annotations

import json

import pytest

from application.handlers.manus_stage import ManusStageConfig
from application.handlers.pipeline import AcquisitionPipelineHandler
from application.usecases.campaigns import CreateCampaign
from infrastructure.providers.manus import KeyLedger, TaskDetail
from infrastructure.repos.system import JobRuntimePg, PlansReaderPg
from runtime import leasing
from tests.v6.conftest import SAMPLE_ICP

@pytest.fixture(autouse=True)
def _leave_outbox_as_found(db):
    """These runs emit domain events nobody relays. test_outbox_relay assumes
    an empty outbox, so remove only the rows created during this test."""
    with db.tx_system() as conn, conn.cursor() as cur:
        before = {r["event_id"] for r in cur.execute(
            "SELECT event_id FROM events.outbox").fetchall()}
    yield
    with db.tx_system() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM events.outbox WHERE NOT (event_id = ANY(%s))",
                    (list(before),))


PAGE = '<a href="tel:+966501112222">+966 50 111 2222</a> info@alpha.sa'


class FakeManus:
    def __init__(self):
        self.created: list[str] = []
        self.status = "running"
        self.answer = json.dumps([
            {"name": "Alpha Dental", "website": "https://alpha.sa",
             "phone": "+966 50 111 2222", "email": "info@alpha.sa"},
            {"name": "Ghost Clinic", "website": "https://ghost.sa",
             "phone": "+966 55 999 9999", "email": "made-up@ghost.sa"},
        ])

    def factory(self, key: str):
        outer = self

        class C:
            def create_task(self, prompt):
                outer.created.append(prompt)
                return f"T{len(outer.created)}"

            def task_detail(self, task_id):
                return TaskDetail(outer.status, 48 if outer.status == "stopped" else 5)

            def final_answer(self, task_id):
                return outer.answer
        return C()


def _fetch(url: str):
    return PAGE if url.startswith("https://alpha.sa") else None


def _config(manus: FakeManus, keys=("k1", "k2")) -> ManusStageConfig:
    return ManusStageConfig(
        ledger_factory=lambda snap: KeyLedger.restore(list(keys), snap)
        if snap else KeyLedger(list(keys), balances={"k1": 300, "k2": 300}),
        client_factory=manus.factory, fetch=_fetch, per_city=15)


ICP = {**SAMPLE_ICP, "discovery": {"engine": "manus"}}


def _campaign(uows, db, org, icp=ICP):
    uc = CreateCampaign(uows, PlansReaderPg(db), JobRuntimePg(db))
    return uc.execute(org, "manus run", icp, budget_cents=0)


def _tick(worker, org, job_id, until=None, max_cycles=40):
    """Run the shared 'default' queue until THIS job is picked up (older jobs
    from other tests may be ahead of it), then return its row."""
    row = leasing.get_job(worker._db, org, job_id)
    for _ in range(max_cycles):
        if not worker.run_once():
            break
        row = leasing.get_job(worker._db, org, job_id)
        if row["state"] != "QUEUED" and row["attempts"] > 0 or row["state"] != "QUEUED":
            break
    return row


def test_slow_task_parks_without_burning_an_attempt_then_resumes(
        db, org, uows, fake_gateway, worker_factory):
    gateway, _ = fake_gateway
    manus = FakeManus()
    handler = AcquisitionPipelineHandler(manus=_config(manus))
    worker = worker_factory({"acquisition.run": handler}, gateway)
    job_id = _campaign(uows, db, org)["job_id"]

    row = _tick(worker, org, job_id)
    assert row["state"] == "WAITING_FOR_CAPACITY"
    assert row["attempts"] == 0                                  # not burned
    assert len(manus.created) == 1                               # one city
    assert row["checkpoint"]["manus"]["tasks"]                   # state survived

    # a worker tick right away must NOT wake it (minimum park age)
    worker.run_maintenance()
    assert leasing.get_job(db, org, job_id)["state"] == "WAITING_FOR_CAPACITY"

    manus.status = "stopped"
    assert leasing.wake_parked(db) >= 1
    for _ in range(8):
        row = _tick(worker, org, job_id)
        if row["state"] in ("READY_FOR_REVIEW", "PARTIAL_SUCCESS"):
            break
    assert row["state"] == "READY_FOR_REVIEW"
    assert len(manus.created) == 1                               # never paid twice


def test_only_contacts_confirmed_on_the_company_site_are_stored(
        db, org, uows, fake_gateway, worker_factory):
    gateway, _ = fake_gateway
    manus = FakeManus()
    manus.status = "stopped"
    worker = worker_factory(
        {"acquisition.run": AcquisitionPipelineHandler(manus=_config(manus))}, gateway)
    job_id = _campaign(uows, db, org)["job_id"]
    for _ in range(8):
        row = _tick(worker, org, job_id)
        if row["state"] in ("READY_FOR_REVIEW", "PARTIAL_SUCCESS", "FAILED"):
            break

    with uows(org) as tx:
        leads = tx.repos.projects.list_leads()
    blob = repr(leads)
    assert "Alpha" in blob or "alpha.sa" in blob
    assert "ghost" not in blob.lower() or "made-up@ghost.sa" not in blob
    assert "made-up@ghost.sa" not in blob and "+966559999999" not in blob
    assert "info@alpha.sa" not in blob                           # masked, ADR-0006


def test_restart_mid_wait_does_not_resubmit(db, org, uows, fake_gateway, worker_factory):
    gateway, _ = fake_gateway
    manus = FakeManus()
    job_id = _campaign(uows, db, org)["job_id"]
    first = worker_factory(
        {"acquisition.run": AcquisitionPipelineHandler(manus=_config(manus))}, gateway)
    _tick(first, org, job_id)
    assert len(manus.created) == 1

    leasing.wake_parked(db)
    second = worker_factory(                                       # a brand-new process
        {"acquisition.run": AcquisitionPipelineHandler(manus=_config(manus))}, gateway)
    _tick(second, org, job_id)
    assert len(manus.created) == 1


def test_icp_without_manus_never_touches_it(db, org, uows, fake_gateway, worker_factory):
    from tests.v6.conftest import seed_results
    gateway, fakes = fake_gateway
    seed_results(fakes["search"])
    manus = FakeManus()
    worker = worker_factory(
        {"acquisition.run": AcquisitionPipelineHandler(manus=_config(manus))}, gateway)
    job_id = _campaign(uows, db, org, icp=SAMPLE_ICP)["job_id"]
    for _ in range(12):
        row = _tick(worker, org, job_id)
        if row["state"] in ("READY_FOR_REVIEW", "PARTIAL_SUCCESS", "FAILED"):
            break
    assert manus.created == []
    assert row["state"] == "READY_FOR_REVIEW"


def test_manus_requested_but_no_keys_fails_loudly_not_silently(
        db, org, uows, fake_gateway, worker_factory):
    gateway, _ = fake_gateway
    worker = worker_factory(
        {"acquisition.run": AcquisitionPipelineHandler(manus=None)}, gateway)
    job_id = _campaign(uows, db, org)["job_id"]
    for _ in range(4):
        row = _tick(worker, org, job_id)
        if row["state"] in ("FAILED", "READY_FOR_REVIEW", "PARTIAL_SUCCESS"):
            break
    assert row["state"] == "FAILED"
    assert "manus" in (row["last_error"] or "").lower()
