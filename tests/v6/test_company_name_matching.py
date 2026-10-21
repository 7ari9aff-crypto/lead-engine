"""Integration: Arabic-aware company matching against real Postgres.

Covers the SQL (find_by_name_key), the migration (name_key column), tenant
isolation, backward compatibility with rows created before the migration, and
the handler decision that must never merge two different businesses."""
from __future__ import annotations

import uuid

from application.handlers.pipeline import AcquisitionPipelineHandler
from domain.acquisition.company import name_key


def _create(tx, name, domain=None, city="Riyadh", with_key=True):
    cid = str(uuid.uuid4())
    tx.repos.companies.create_company(
        cid, name, domain, "SA", "dental", city,
        name_key=(name_key(name) or None) if with_key else None)
    return cid


def test_arabic_spelling_variants_resolve_to_the_same_company(db, org, uows):
    with uows(org) as tx:
        cid = _create(tx, "مركز أبراج الطبي")
    with uows(org) as tx:
        found = tx.repos.companies.find_by_name_key(name_key("مركز ابراج الطبى"))
    assert found is not None and str(found["id"]) == cid


def test_name_key_column_is_persisted(db, org, uows):
    with uows(org) as tx:
        cid = _create(tx, "عيادة الزهراء لطب الأسنان")
        row = tx.cursor.execute(
            "SELECT name_key FROM company_identity.companies WHERE id = %s", (cid,)
        ).fetchone()
    assert row["name_key"] == name_key("عيادة الزهراء لطب الأسنان") == "زهراء"


def test_generic_name_gets_no_key_so_it_can_never_match(db, org, uows):
    with uows(org) as tx:
        cid = _create(tx, "Dental Clinic")
        row = tx.cursor.execute(
            "SELECT name_key FROM company_identity.companies WHERE id = %s", (cid,)
        ).fetchone()
    assert row["name_key"] is None


def test_rows_created_before_the_migration_are_still_found(db, org, uows):
    """Deploying code before the backfill must not lose matches: a legacy row has
    name_key NULL and is found through the old canonical_name comparison."""
    with uows(org) as tx:
        cid = _create(tx, "zahra", with_key=False)      # canonical == key, no name_key
    with uows(org) as tx:
        found = tx.repos.companies.find_by_name_key("zahra")
    assert found is not None and str(found["id"]) == cid


def test_other_tenants_companies_are_invisible(db, org, uows):
    from application.usecases.onboard import OnboardOrg
    from infrastructure.repos.system import BootstrapPg

    other = OnboardOrg(BootstrapPg(db)).execute(
        f"org-{uuid.uuid4().hex[:10]}", "Other Org", "pro",
        f"owner-{uuid.uuid4().hex[:8]}")["org_id"]
    with uows(other) as tx:
        _create(tx, "Secret Competitor Dental")
    with uows(org) as tx:
        assert tx.repos.companies.find_by_name_key(name_key("Secret Competitor Dental")) is None


def test_merged_companies_are_not_matched(db, org, uows):
    with uows(org) as tx:
        a = _create(tx, "Noor Specialist")
        b = _create(tx, "Noor Specialist Hospital X")
        tx.cursor.execute("UPDATE company_identity.companies SET merged_into_id = %s WHERE id = %s",
                       (b, a))
    with uows(org) as tx:
        found = tx.repos.companies.find_by_name_key(name_key("Noor Specialist"))
    assert found is None or str(found["id"]) != a


# -- the handler's decision: name alone must never override domain/city -----
def _match(tx, title, domain, city):
    return AcquisitionPipelineHandler._name_match(title, domain, city, tx)


def test_same_name_different_domain_is_not_merged(db, org, uows):
    """Real prod case: several 'best dental clinic in Riyadh' pages on different
    sites collapsed into one company."""
    with uows(org) as tx:
        _create(tx, "أفضل عيادة أسنان بالرياض", "okclinics.sa")
    with uows(org) as tx:
        assert _match(tx, "افضل عياده اسنان في الرياض", "ddclinic.sa", "Riyadh") is None


def test_same_name_same_domain_is_merged(db, org, uows):
    with uows(org) as tx:
        cid = _create(tx, "Al Zahra Dental Clinic", "alzahradental.com", "Jeddah")
    with uows(org) as tx:
        hit = _match(tx, "Al Zahra Dental Center (@alzahradental)", "alzahradental.com", "Jeddah")
    assert hit is not None and str(hit["id"]) == cid


def test_existing_company_without_domain_can_be_matched_by_name(db, org, uows):
    with uows(org) as tx:
        cid = _create(tx, "Al Zahra Dental Center (@alzahradental)", None, "Jeddah")
    with uows(org) as tx:
        hit = _match(tx, "Al Zahra Dental Clinic", "alzahradental.com", "Jeddah")
    assert hit is not None and str(hit["id"]) == cid


def test_same_name_different_city_is_not_merged(db, org, uows):
    with uows(org) as tx:
        _create(tx, "Elite Dental", None, "Jeddah")
    with uows(org) as tx:
        assert _match(tx, "Elite Dental", None, "Riyadh") is None


def test_generic_title_never_matches(db, org, uows):
    with uows(org) as tx:
        _create(tx, "Dental Clinic", "obeidhospitals.com")
    with uows(org) as tx:
        assert _match(tx, "Dental Clinic", None, "Riyadh") is None


def test_ingest_names_company_by_domain_confirmed_segment_and_keeps_raw_title(
        db, org, uows, fake_gateway, worker_factory):
    """Full journey: a result titled '<tagline> | kimshealth' on kimshealth.co is
    stored as company 'kimshealth', while the raw title stays as provenance."""
    from application.usecases.campaigns import CreateCampaign
    from infrastructure.repos.system import JobRuntimePg, PlansReaderPg
    from runtime import leasing
    from tests.v6.conftest import SAMPLE_ICP

    gateway, fakes = fake_gateway
    raw_title = "dental care services in saudi arabia | kimshealth"
    fakes["search"]._results = [
        {"match": "dental clinic in Riyadh", "always": True,
         "url": "https://kimshealth.co/dental", "title": raw_title,
         "snippet": "dental clinic in Riyadh"},
    ]
    # The pipeline emits outbox events. Drain them with a relay (as the other
    # e2e tests do) so no unpublished events leak into tests that assume an
    # empty outbox (test_outbox_relay asserts exact tick() counts).
    from infrastructure.events.relay import IdempotentConsumer, OutboxRelay

    relay = OutboxRelay(db, consumer=IdempotentConsumer(db, "name-test", lambda e: None))
    worker = worker_factory({"acquisition.run": AcquisitionPipelineHandler()}, gateway,
                            relay=relay)
    job_id = CreateCampaign(uows, PlansReaderPg(db), JobRuntimePg(db)).execute(
        org, "Riyadh dental", SAMPLE_ICP, budget_cents=0)["job_id"]
    for _ in range(12):
        worker.run_once()
        if leasing.get_job(db, org, job_id)["state"] in (
                "READY_FOR_REVIEW", "PARTIAL_SUCCESS", "FAILED", "CANCELLED"):
            break

    while relay.tick():            # publish everything this run emitted
        pass

    with uows(org) as tx:
        co = tx.cursor.execute(
            "SELECT canonical_name, name_key FROM company_identity.companies "
            "WHERE domain = 'kimshealth.co'").fetchone()
        obs = tx.cursor.execute(
            "SELECT value FROM claims_evidence.company_observations WHERE field = 'name' "
            "AND company_id = (SELECT id FROM company_identity.companies "
            "WHERE domain = 'kimshealth.co')").fetchall()
    assert co["canonical_name"] == "kimshealth"
    assert co["name_key"] == "kimshealth"
    assert [o["value"] for o in obs] == [raw_title]       # provenance untouched
