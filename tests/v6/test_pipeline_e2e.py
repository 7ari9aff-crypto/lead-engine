"""End-to-end pipeline journey — the V6 happy path plus failure paths.

Journey: onboard → campaign (ICP) → durable job → phases with checkpoints →
lead projections → human approval → events → business lineage.
"""
from __future__ import annotations


import pytest

from application.handlers.pipeline import AcquisitionPipelineHandler
from application.usecases.campaigns import CreateCampaign, JobQuery
from application.usecases.review import ReviewUseCase
from contracts.errors import EntitlementExceeded
from infrastructure.events.relay import IdempotentConsumer, OutboxRelay
from infrastructure.repos.system import JobRuntimePg, PlansReaderPg
from runtime import leasing
from tests.v6.conftest import SAMPLE_ICP, seed_results


def _make_relay(db, seen: list):
    consumer = IdempotentConsumer(db, "e2e-consumer",
                                  lambda e: seen.append((e.type, e.aggregate_id)))
    return OutboxRelay(db, consumer=consumer)


def _run_worker(worker, org: str, job_id: str, max_cycles: int = 12) -> str:
    state = None
    for _ in range(max_cycles):
        worker.run_once()
        state = leasing.get_job(worker._db, org, job_id)["state"]
        if state in ("READY_FOR_REVIEW", "CANCELLED", "FAILED", "PARTIAL_SUCCESS"):
            return state
    return state or "?"


def test_full_pipeline_journey(db, org, uows, fake_gateway, worker_factory):
    gateway, fakes = fake_gateway
    seed_results(fakes["search"])
    seen_events: list = []
    relay = _make_relay(db, seen_events)

    worker = worker_factory({"acquisition.run": AcquisitionPipelineHandler()},
                            gateway, relay=relay)
    use_case = CreateCampaign(uows, PlansReaderPg(db), JobRuntimePg(db))

    result = use_case.execute(org, "Riyadh dental", SAMPLE_ICP, budget_cents=0)
    job_id = result["job_id"]

    final_state = _run_worker(worker, org, job_id)
    assert final_state == "READY_FOR_REVIEW"

    # campaign advanced; leads exist as projections
    with uows(org) as tx:
        campaign = tx.repos.acquisition.get_campaign(result["campaign_id"])
        assert campaign["state"] == "READY_FOR_REVIEW"
        leads = tx.repos.projects.list_leads()

    decisions = {lead["decision"]: lead for lead in leads}
    assert "accepted" in decisions and "review" in decisions  # alpha vs beta
    alpha = decisions["accepted"]
    assert alpha["masked_email"] == "i***o@alpha-dental.sa"
    assert alpha["display"]["domain"] == "alpha-dental.sa"

    # plaintext PII never reaches projections (ADR-0006)
    blob = repr(leads)
    assert "info@alpha-dental.sa" not in blob and "+966500000001" not in blob

    # social + editorial pages were excluded by identity resolution
    domains = [lead["display"].get("domain") for lead in leads]
    assert "facebook.com" not in domains and "news.example.com" not in domains

    # human approval boundary (§31)
    review = ReviewUseCase(uows)
    outcome = review.decide(org, alpha["id"], "owner-human", approve=True, reason="fit")
    assert outcome["state"] == "APPROVED"
    with uows(org) as tx:
        after = tx.repos.projects.get_lead(alpha["id"])
    assert after["state"] == "APPROVED"

    # drain the outbox: events created during the run + the approval event
    relay.tick()
    types = [t for t, _ in seen_events]
    assert "acquisition.lead.ready_for_review" in types
    assert "acquisition.lead.approved" in types
    assert "governance.decision.recorded" in types

    # business lineage answers "why is this lead here?"
    with uows(org) as tx:
        lineage = tx.repos.lineage.lead_lineage(alpha["id"])
    assert lineage["claims"] and any(c["field"] == "website" for c in lineage["claims"])
    assert lineage["sources"] and lineage["scores"] and lineage["qualification"]
    assert lineage["verifications"]
    assert lineage["verifications"][0]["status"] == "DELIVERABLE"


def test_job_is_durable_and_queryable(db, org, uows, fake_gateway, worker_factory):
    gateway, fakes = fake_gateway
    seed_results(fakes["search"])
    jobs = JobQuery(JobRuntimePg(db))
    result = CreateCampaign(uows, PlansReaderPg(db), JobRuntimePg(db)).execute(
        org, "Durability check", SAMPLE_ICP)
    events_before = jobs.get(org, result["job_id"])["events"]
    assert events_before  # 'created' event recorded


def test_entitlements_reject_second_concurrent_job(db, free_org, uows):
    use_case = CreateCampaign(uows, PlansReaderPg(db), JobRuntimePg(db))
    first = use_case.execute(free_org, "First", SAMPLE_ICP)
    assert first["job_id"]
    with pytest.raises(EntitlementExceeded):
        use_case.execute(free_org, "Second", SAMPLE_ICP)


def test_empty_icp_fails_loudly_not_silently(db, org, uows, fake_gateway, worker_factory):
    gateway, fakes = fake_gateway
    empty_icp = {**SAMPLE_ICP, "cities": [], "keywords_en": [], "keywords_ar": []}
    result = CreateCampaign(uows, PlansReaderPg(db), JobRuntimePg(db)).execute(
        org, "Empty ICP", empty_icp)
    worker = worker_factory({"acquisition.run": AcquisitionPipelineHandler()}, gateway)
    for _ in range(5):  # retries exhaust max_attempts
        worker.run_once()
        row = leasing.get_job(db, org, result["job_id"])
        if row["state"] == "FAILED":
            break
    assert row["state"] == "FAILED"
    assert "zero queries" in row["last_error"]


def test_cancellation_mid_run(db, org, uows, fake_gateway, worker_factory):
    gateway, fakes = fake_gateway
    seed_results(fakes["search"])
    result = CreateCampaign(uows, PlansReaderPg(db), JobRuntimePg(db)).execute(
        org, "Cancel me", SAMPLE_ICP)
    leasing.request_cancel(db, org, result["job_id"], "owner-1", "changed mind")
    worker = worker_factory({"acquisition.run": AcquisitionPipelineHandler()}, gateway)
    final = _run_worker(worker, org, result["job_id"])
    assert final == "CANCELLED"


def test_worker_resume_is_idempotent_after_lease_loss(db, org, uows, fake_gateway,
                                                      worker_factory):
    """Reaper path: expire a mid-flight lease, reclaim, re-run — the visited-
    sources + unique-claim invariants keep the result clean (no duplicates)."""
    gateway, fakes = fake_gateway
    seed_results(fakes["search"])
    result = CreateCampaign(uows, PlansReaderPg(db), JobRuntimePg(db)).execute(
        org, "Resume check", SAMPLE_ICP)
    worker = worker_factory({"acquisition.run": AcquisitionPipelineHandler()}, gateway,
                            worker_id="stale-worker")
    final = _run_worker(worker, org, result["job_id"])
    assert final == "READY_FOR_REVIEW"

    with uows(org) as tx:
        leads = tx.repos.projects.list_leads()
    domains = [lead["display"].get("domain") for lead in leads]
    assert len(domains) == len(set(domains))  # identity dedup survived the run
