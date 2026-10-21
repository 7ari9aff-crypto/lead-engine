"""CRM push: eligibility, mapping, idempotency, dry-run default, no leakage."""
import pytest

from lead_engine import crm_push as c


def lead(**kw):
    base = {"lead_id": "L1", "name": "Smile Dental", "domain": "smile.sa",
            "email": "Owner@Smile.sa", "email_status": "DELIVERABLE",
            "stage": "ACCEPTED", "legal_decision": "ACCEPTED",
            "decision_maker": "Ahmed Al Harbi", "decision_maker_title": "CEO",
            "phone": "+966500000000", "city": "Riyadh", "country": "SA"}
    base.update(kw)
    return base


NOT_SUPPRESSED = lambda e: (False, None)  # noqa: E731


class Resp:
    def __init__(self, code=200, text=""):
        self.status_code, self.text = code, text


def test_accepted_lead_is_eligible():
    assert c.eligibility(lead(), NOT_SUPPRESSED) is None


@pytest.mark.parametrize("kw,reason", [
    ({"stage": "REVIEW"}, c.SKIP_STAGE),
    ({"stage": "REJECTED"}, c.SKIP_STAGE),
    ({"legal_decision": "REJECTED"}, c.SKIP_LEGAL),
    ({"legal_decision": "retention-erased"}, c.SKIP_ERASED),
    ({"disposition": "REJECT"}, c.SKIP_REVIEWER_REJECTED),
    ({"email": None}, c.SKIP_NO_EMAIL),
    ({"email": "   "}, c.SKIP_NO_EMAIL),
    ({"email": "not-an-email"}, c.SKIP_BAD_EMAIL),
    ({"email_status": "INVALID"}, c.SKIP_EMAIL_STATUS),
])
def test_ineligible_reasons(kw, reason):
    assert c.eligibility(lead(**kw), NOT_SUPPRESSED) == reason


def test_erased_wins_even_if_everything_else_is_fine():
    assert c.eligibility(lead(legal_decision="retention-erased", stage="ACCEPTED"),
                         NOT_SUPPRESSED) == c.SKIP_ERASED


def test_suppressed_email_is_skipped_using_normalized_address():
    seen = []
    def sup(e):
        seen.append(e)
        return (True, "unsubscribed")
    assert c.eligibility(lead(), sup) == c.SKIP_SUPPRESSED
    assert seen == ["owner@smile.sa"]


def test_reviewer_approved_is_pushable():
    assert c.eligibility(lead(disposition="APPROVE_CONTACT"), NOT_SUPPRESSED) is None


def test_mapping_uses_email_as_id_and_omits_blanks():
    m = c.to_hubspot_contact(lead(phone="", linkedin=None))
    assert m["id"] == "owner@smile.sa" and m["idProperty"] == "email"
    p = m["properties"]
    assert p["firstname"] == "Ahmed" and p["lastname"] == "Al Harbi"
    assert p["company"] == "Smile Dental" and p["jobtitle"] == "CEO"
    assert p["website"] == "https://smile.sa"
    assert "phone" not in p and "hs_linkedin_url" not in p


def test_single_word_name_and_missing_name():
    assert c._split_name("Madonna") == ("Madonna", "")
    assert c._split_name(None) == ("", "")


def test_plan_dedupes_same_email_case_insensitively():
    leads = [lead(lead_id="A"), lead(lead_id="B", email="OWNER@smile.sa")]
    p = c.plan(leads, NOT_SUPPRESSED)
    assert len(p["inputs"]) == 1
    assert p["skipped"] == [{"lead_id": "B", "reason": c.SKIP_DUPLICATE}]


def test_dry_run_is_default_and_sends_nothing():
    calls = []
    out = c.push([lead()], is_suppressed=NOT_SUPPRESSED,
                 access_token=lambda: pytest.fail("token must not be fetched in dry run"),
                 http_post=lambda *a, **k: calls.append(1))
    assert out["dry_run"] is True and out["eligible"] == 1 and out["pushed"] == 0
    assert calls == []


def test_real_push_hits_only_hubspot_with_bearer_and_batches():
    calls = []
    def post(url, json=None, headers=None, timeout=None):
        calls.append((url, len(json["inputs"]), headers["Authorization"]))
        return Resp(200)
    leads = [lead(lead_id=str(i), email=f"p{i}@x.sa") for i in range(250)]
    out = c.push(leads, is_suppressed=NOT_SUPPRESSED, access_token=lambda: "tok",
                 http_post=post, dry_run=False)
    assert out["pushed"] == 250 and out["failed_batches"] == []
    assert [n for _, n, _ in calls] == [100, 100, 50]
    assert all(u == "https://api.hubapi.com/crm/v3/objects/contacts/batch/upsert"
               for u, _, _ in calls)
    assert all(a == "Bearer tok" for _, _, a in calls)


def test_failed_batch_is_reported_and_others_continue():
    state = {"n": 0}
    def post(url, json=None, headers=None, timeout=None):
        state["n"] += 1
        return Resp(429, "rate limited") if state["n"] == 1 else Resp(200)
    leads = [lead(lead_id=str(i), email=f"p{i}@x.sa") for i in range(150)]
    out = c.push(leads, is_suppressed=NOT_SUPPRESSED, access_token=lambda: "t",
                 http_post=post, dry_run=False)
    assert out["pushed"] == 50
    assert out["failed_batches"][0]["status"] == 429


def test_network_exception_is_contained_and_leaks_no_token_or_pii():
    def post(*a, **k):
        raise ConnectionError("boom owner@smile.sa Bearer SECRET")
    out = c.push([lead()], is_suppressed=NOT_SUPPRESSED,
                 access_token=lambda: "SECRET", http_post=post, dry_run=False)
    assert out["pushed"] == 0
    blob = str(out)
    assert "SECRET" not in blob and "owner@smile.sa" not in blob
    assert out["failed_batches"][0]["error"] == "ConnectionError"


def test_summary_counts_skips_by_reason_without_exposing_emails():
    out = c.push([lead(), lead(lead_id="X", stage="REVIEW"),
                  lead(lead_id="Y", email=None)],
                 is_suppressed=NOT_SUPPRESSED, access_token=lambda: "t",
                 http_post=lambda *a, **k: Resp(), dry_run=True)
    assert out["skipped_by_reason"] == {c.SKIP_STAGE: 1, c.SKIP_NO_EMAIL: 1}
    assert "@" not in str(out["skipped_detail"])


def test_live_data_shape_regression_accepted_but_erased_is_never_pushed():
    """Production (Oct 2026) held 28 leads with stage=ACCEPTED AND
    legal_decision='retention-erased'. A stage-only filter would have sent
    already-erased personal data to a third-party CRM."""
    erased = [lead(lead_id=f"E{i}", email=f"e{i}@x.sa", stage="ACCEPTED",
                   legal_decision="retention-erased") for i in range(28)]
    out = c.push(erased, is_suppressed=NOT_SUPPRESSED, access_token=lambda: "t",
                 http_post=lambda *a, **k: pytest.fail("must not send"),
                 dry_run=False)
    assert out["eligible"] == 0 and out["pushed"] == 0
    assert out["skipped_by_reason"] == {c.SKIP_ERASED: 28}
