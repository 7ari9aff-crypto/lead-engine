"""Manus async discovery: key ledger, task lifecycle, parsing, verification.

Manus is NOT a synchronous search adapter (minutes per task, credit metered).
These tests pin the pieces that make it safe to run unattended:
credit-aware key choice, resumable task state, honest parsing, and the rule
that nothing Manus says is trusted until the company's own page confirms it.
"""
from __future__ import annotations

import json

import httpx
import pytest

from infrastructure.providers.manus import (
    KeyLedger,
    ManusClient,
    ManusError,
    parse_companies,
    verify_company,
)


# ----------------------------------------------------------------- ledger
def test_ledger_prefers_highest_remaining_balance():
    led = KeyLedger(["a", "b", "c"], balances={"a": 300, "b": 1300, "c": 120}, floor=30)
    assert led.pick() == "b"


def test_ledger_skips_keys_at_or_under_floor():
    led = KeyLedger(["a", "b"], balances={"a": 30, "b": 29}, floor=30)
    assert led.pick() is None
    led.balances["b"] = 31
    assert led.pick() == "b"


def test_ledger_charge_reduces_balance_and_rotates():
    led = KeyLedger(["a", "b"], balances={"a": 100, "b": 90}, floor=30)
    assert led.pick() == "a"
    led.charge("a", 60)                    # a: 40 left; b is now higher
    assert led.balances["a"] == 40
    assert led.pick() == "b"


def test_ledger_reserve_prevents_overspending_one_key():
    """Concurrent tasks on one key must be counted before they finish."""
    led = KeyLedger(["a", "b"], balances={"a": 100, "b": 90}, floor=30)
    first = led.reserve(estimate=50)
    second = led.reserve(estimate=50)
    assert first == "a" and second == "b"   # a is held (100-50=50), b now leads
    led.release("a", 50)
    assert led.balances["a"] == 100


def test_ledger_returns_none_when_everything_is_spent():
    led = KeyLedger(["a"], balances={"a": 31}, floor=30)
    assert led.reserve(estimate=20) is None   # 31-20 < floor: refuse, don't strand a task


def test_ledger_unknown_balance_is_treated_as_unknown_not_zero():
    led = KeyLedger(["a"], balances={}, floor=30, default_balance=300)
    assert led.pick() == "a"


def test_ledger_snapshot_contains_no_key_values():
    led = KeyLedger(["secret-key-1"], balances={"secret-key-1": 100}, floor=30)
    assert "secret-key-1" not in json.dumps(led.snapshot())


def test_ledger_roundtrip_through_checkpoint():
    led = KeyLedger(["a", "b"], balances={"a": 100, "b": 90}, floor=30)
    led.charge("a", 10)
    restored = KeyLedger.restore(["a", "b"], led.snapshot(), floor=30)
    assert restored.balances == {"a": 90, "b": 90}


# ----------------------------------------------------------------- client
def _client(handler):
    return ManusClient("k1", transport=httpx.MockTransport(handler))


def test_create_task_sends_key_header_and_hides_from_list():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["path"] = req.url.path
        seen["key"] = req.headers["x-manus-api-key"]
        seen["body"] = json.loads(req.read())
        return httpx.Response(200, json={"ok": True, "task_id": "T1"})

    assert _client(handler).create_task("find clinics") == "T1"
    assert seen["path"] == "/v2/task.create"
    assert seen["key"] == "k1"
    assert seen["body"] == {"message": {"content": "find clinics"},
                            "hide_in_task_list": True}


def test_detail_reports_status_and_credit_usage():
    def handler(req):
        return httpx.Response(200, json={"ok": True, "task": {
            "status": "stopped", "credit_usage": 48}})

    d = _client(handler).task_detail("T1")
    assert d.finished and d.credits == 48 and not d.failed


def test_running_task_is_not_finished():
    c = _client(lambda r: httpx.Response(200, json={"ok": True, "task": {
        "status": "running", "credit_usage": 5}}))
    assert not c.task_detail("T1").finished


def test_error_status_is_failed():
    c = _client(lambda r: httpx.Response(200, json={"ok": True, "task": {
        "status": "error", "credit_usage": 3}}))
    d = c.task_detail("T1")
    assert d.failed and d.finished


def test_final_answer_is_newest_assistant_message():
    msgs = [
        {"type": "status_update", "status_update": {"agent_status": "stopped"}},
        {"type": "assistant_message", "assistant_message": {"content": "FINAL"}},
        {"type": "assistant_message", "assistant_message": {"content": "OLDER"}},
    ]
    c = _client(lambda r: httpx.Response(200, json={"ok": True, "messages": msgs,
                                                    "has_more": False}))
    assert c.final_answer("T1") == "FINAL"      # API returns newest first


def test_http_errors_are_classified():
    for code, kind in [(401, "AUTH"), (429, "RATE_LIMIT"), (402, "CAPACITY"),
                       (503, "TRANSIENT")]:
        c = _client(lambda r, code=code: httpx.Response(code, json={}))
        with pytest.raises(ManusError) as exc:
            c.create_task("x")
        assert exc.value.kind == kind


def test_insufficient_credit_body_is_capacity_even_on_200():
    c = _client(lambda r: httpx.Response(200, json={"ok": False,
                                                    "error": {"code": "insufficient_credits"}}))
    with pytest.raises(ManusError) as exc:
        c.create_task("x")
    assert exc.value.kind == "CAPACITY"


# ---------------------------------------------------------------- parsing
def test_parse_plain_json_array():
    text = json.dumps([{"name": "A", "website": "https://a.sa", "phone": "+966 50 111 2222",
                        "email": "info@a.sa", "source": "https://a.sa/contact"}])
    [c] = parse_companies(text)
    assert c["name"] == "A" and c["website"] == "https://a.sa"


def test_parse_tolerates_markdown_fence_and_prose():
    text = "Here you go:\n```json\n[{\"name\":\"A\",\"website\":\"https://a.sa\"}]\n```\nDone."
    assert [c["name"] for c in parse_companies(text)] == ["A"]


def test_parse_drops_rows_without_name_or_website():
    text = json.dumps([{"name": "A", "website": ""}, {"name": "", "website": "https://b.sa"},
                       {"name": "C", "website": "https://c.sa"}])
    assert [c["name"] for c in parse_companies(text)] == ["C"]


def test_parse_garbage_returns_empty_not_exception():
    assert parse_companies("I could not find anything") == []
    assert parse_companies("") == []
    assert parse_companies("[{broken json") == []


def test_parse_dedupes_by_domain():
    text = json.dumps([{"name": "A", "website": "https://www.a.sa/en"},
                       {"name": "A2", "website": "http://a.sa"}])
    assert len(parse_companies(text)) == 1


def test_parse_blank_strings_become_none():
    [c] = parse_companies(json.dumps([{"name": "A", "website": "https://a.sa",
                                       "phone": "  ", "email": ""}]))
    assert c["phone"] is None and c["email"] is None


# ------------------------------------------------------------ verification
PAGE = """<html><body>Contact us: <a href="tel:+966501112222">+966 50 111 2222</a>
Email: <a href="mailto:info@a.sa">info@a.sa</a></body></html>"""


def _fetch(pages):
    def fetch(url: str) -> str | None:
        return pages.get(url)
    return fetch


def test_phone_and_email_confirmed_on_the_company_page():
    company = {"name": "A", "website": "https://a.sa", "phone": "+966 50 111 2222",
               "email": "info@a.sa", "source": None}
    out = verify_company(company, fetch=_fetch({"https://a.sa": PAGE}))
    assert out["phone_verified"] is True and out["email_verified"] is True
    assert out["phone"] == "+966501112222"


def test_email_not_on_page_is_dropped_not_kept():
    company = {"name": "A", "website": "https://a.sa", "phone": None,
               "email": "guess@a.sa", "source": None}
    out = verify_company(company, fetch=_fetch({"https://a.sa": PAGE}))
    assert out["email"] is None and out["email_verified"] is False


def test_phone_matches_regardless_of_formatting():
    company = {"name": "A", "website": "https://a.sa", "phone": "0501112222",
               "email": None, "source": None}
    page = "<p>Call 050-111-2222 today</p>"
    out = verify_company(company, fetch=_fetch({"https://a.sa": page}))
    assert out["phone_verified"] is True


def test_unreachable_site_means_nothing_is_verified():
    company = {"name": "A", "website": "https://dead.sa", "phone": "+966501112222",
               "email": "x@dead.sa", "source": None}
    out = verify_company(company, fetch=_fetch({}))
    assert out["phone_verified"] is False and out["email_verified"] is False
    assert out["phone"] is None and out["email"] is None
    assert out["site_reachable"] is False


def test_contact_subpage_is_tried_when_homepage_lacks_the_data():
    company = {"name": "A", "website": "https://a.sa", "phone": None,
               "email": "info@a.sa", "source": None}
    pages = {"https://a.sa": "<p>home</p>", "https://a.sa/contact": PAGE}
    out = verify_company(company, fetch=_fetch(pages))
    assert out["email_verified"] is True


def test_email_on_a_different_domain_still_needs_page_evidence():
    company = {"name": "A", "website": "https://a.sa", "phone": None,
               "email": "owner@gmail.com", "source": None}
    out = verify_company(company, fetch=_fetch({"https://a.sa": PAGE}))
    assert out["email_verified"] is False and out["email"] is None
