"""status_table must expire stale provider states like the router does.

Regression found by reading the live dashboard: `gemini/reasoning` showed
"cooling down" on the Providers page while its cooldown_until was 26 days in
the past — /api/status reads status_table(), which (unlike providers_for_task)
had no expiry pass, so an expired cooldown rendered as a live capacity block.
"""
import pytest

from lead_engine.db import utcnow
from lead_engine.registry import Registry
from tests.conftest import seed_control_plane


def _fresh_db(tmp_path):
    from lead_engine.db import open_db

    db = open_db(tmp_path / "t.sqlite3")
    seed_control_plane(db)
    return db


def test_status_table_clears_expired_cooldown(tmp_path):
    db = _fresh_db(tmp_path)
    Registry(db).seed_if_empty()
    # set a cooldown that expired long ago, the way a 429 would have
    db.execute(
        "UPDATE providers SET status='cooldown', status_reason='429',"
        " cooldown_until=? WHERE name='gemini' AND task='reasoning'",
        ("2020-01-01T00:00:00Z",),
    )
    rows = {(r["name"], r["task"]): r for r in Registry(db).status_table()}
    row = rows[("gemini", "reasoning")]
    assert row["status"] == "active", "an expired cooldown must not render as live"
    # the correction is persisted, not just displayed
    assert db.one("SELECT status FROM providers WHERE name='gemini' AND task='reasoning'")["status"] == "active"


def test_status_table_keeps_future_cooldown(tmp_path):
    db = _fresh_db(tmp_path)
    Registry(db).seed_if_empty()
    future = "2999-01-01T00:00:00Z"
    db.execute(
        "UPDATE providers SET status='cooldown', status_reason='429',"
        " cooldown_until=? WHERE name='gemini' AND task='reasoning'",
        (future,),
    )
    rows = {(r["name"], r["task"]): r for r in Registry(db).status_table()}
    assert rows[("gemini", "reasoning")]["status"] == "cooldown"


def test_status_table_rolls_over_monthly_quota(tmp_path):
    db = _fresh_db(tmp_path)
    Registry(db).seed_if_empty()
    # tavily has a monthly quota; pretend last month's window is exhausted
    db.execute(
        "UPDATE providers SET quota_used=1000, period_start=?, status='exhausted'"
        " WHERE name='tavily' AND task='web_search'",
        ("2020-01-01T00:00:00Z",),
    )
    rows = {(r["name"], r["task"]): r for r in Registry(db).status_table()}
    row = rows[("tavily", "web_search")]
    assert row["quota_used"] == 0
    assert row["status"] == "active"


def test_status_table_and_router_agree_on_the_same_row(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    db = _fresh_db(tmp_path)
    Registry(db).seed_if_empty()
    db.execute(
        "UPDATE providers SET status='cooldown', cooldown_until=?"
        " WHERE name='gemini' AND task='reasoning'",
        ("2020-01-01T00:00:00Z",),
    )
    status_rows = {(r["name"], r["task"]): r for r in Registry(db).status_table()}
    router_rows = {(r["name"], r["task"]): r for r in Registry(db).providers_for_task("reasoning")}
    assert status_rows[("gemini", "reasoning")]["status"] == router_rows[("gemini", "reasoning")]["status"]
    assert utcnow()  # sanity: clock helper used in the paths above
