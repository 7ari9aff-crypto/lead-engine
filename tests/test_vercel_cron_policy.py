"""Static guard: vercel.json must not declare cron jobs the plan cannot run.

Why this exists: Vercel rejects the ENTIRE deployment when a `crons` entry is
more frequent than the account's plan allows — on Hobby that means anything
faster than once per day. The rejection is not a warning: `vercel deploy --prod`
fails with "Hobby accounts are limited to daily cron jobs", so production
silently stops shipping while every CI job stays green (CI builds a Docker
image; the Vercel deploy is a separate manual step). The 5-minute worker tick
added to vercel.json blocked all production deployments for a week.

Durable execution therefore lives in `.github/workflows/worker-tick.yml`
(scheduled GET of /api/cron/worker with the bearer), not in Vercel crons.
"""
import json
import re
from pathlib import Path

VERCEL_JSON = Path(__file__).resolve().parents[1] / "vercel.json"

_SINGLE = re.compile(r"\A\d{1,2}\Z")


def _is_pinned(token: str) -> bool:
    """A single fixed value — '0' yes; '*', '*/5', '0,12', '5-7' no."""
    return bool(_SINGLE.match(token))


def fires_more_than_once_per_day(expr: str) -> bool:
    """Conservative rule: a schedule can only be <= 1 firing/day when BOTH the
    minute and the hour are pinned to single values. Day/month/weekday can only
    narrow it further, so they cannot rescue an unconstrained hour."""
    parts = expr.split()
    assert len(parts) == 5, f"not a 5-field cron expression: {expr!r}"
    return not (_is_pinned(parts[0]) and _is_pinned(parts[1]))


def test_pinned_cron_predicate():
    """The predicate itself, so the guard cannot rot into vacuity."""
    assert fires_more_than_once_per_day("*/5 * * * *")      # worker tick
    assert fires_more_than_once_per_day("0 * * * *")         # hourly
    assert fires_more_than_once_per_day("0,12 * * * *")      # twice daily
    assert not fires_more_than_once_per_day("0 3 * * *")     # nightly
    assert not fires_more_than_once_per_day("30 4 * * 1")    # weekly


def test_vercel_crons_within_plan_limits():
    if not VERCEL_JSON.exists():
        return
    crons = json.loads(VERCEL_JSON.read_text(encoding="utf-8")).get("crons", [])
    too_fast = [c["schedule"] for c in crons
                if fires_more_than_once_per_day(c["schedule"])]
    assert not too_fast, (
        f"vercel.json crons {too_fast} run more often than daily. This plan "
        "rejects the whole deployment (Hobby: daily only), which blocks ALL "
        "production shipping. Drive /api/cron/worker from "
        ".github/workflows/worker-tick.yml instead."
    )
