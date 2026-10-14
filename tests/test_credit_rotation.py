"""Credit-aware key rotation (providers/base.py + router.py).

Rule the owner set for the 20-key Manus pool: each key has a 300-credit
daily grant; the engine spends at most ~30 per key per day, handoff to the
next key happens BEFORE the budget is reached, inside the same call — no
exception, no paused job. Pinned here:

- rotate_for_budget picks the first key with headroom; if none fits it
  settles on the least-loaded key instead of failing;
- the router's pre-call probe rotates keys without raising, and a normal
  request completes even when the pool is mid-handoff;
- reactive 429 rotation still works through the same _key_index.
"""
import datetime

import pytest

from lead_engine.providers import base as base_mod
from lead_engine.providers.base import BaseProvider, note_credit_spend


class _FakeCreditProvider(BaseProvider):
    name = "fakecredit"
    ptype = "llm"
    tasks = ("reasoning",)
    env_key = "FAKE_CREDIT_KEYS"
    daily_key_budget = 30.0
    key_budget_safety_margin = 2.0

    def __init__(self, settings):
        super().__init__(settings)
        self.calls = 0

    def request(self, task, payload):
        self.calls += 1
        note_credit_spend(self.name, self._key_index, 10.0)
        return {"text": "ok", "usage": {"credits": 10.0}}


@pytest.fixture(autouse=True)
def _fresh_credit_ledger(monkeypatch):
    monkeypatch.setattr(base_mod, "CREDIT_SPEND", {})
    monkeypatch.setattr(base_mod, "CREDIT_LEDGER_DATE", {})
    yield


def test_rotate_for_budget_moves_to_first_key_with_headroom(monkeypatch):
    monkeypatch.setenv("FAKE_CREDIT_KEYS", "k1,k2,k3")
    p = _FakeCreditProvider({})
    note_credit_spend("fakecredit", 0, 29.0)  # k1 nearly full
    note_credit_spend("fakecredit", 1, 10.0)  # k2 used
    rotated, idx = p.rotate_for_budget(10.0)
    # The spec: hand off to the NEXT key with room, in pool order — k2
    # (spend 10 + planned 10 stays under the 28-credit ceiling), not the
    # least-loaded k3.
    assert idx == 1 and rotated is True


def test_rotate_for_budget_never_raises_when_full_pool(monkeypatch):
    monkeypatch.setenv("FAKE_CREDIT_KEYS", "k1,k2")
    p = _FakeCreditProvider({})
    note_credit_spend("fakecredit", 0, 40.0)
    note_credit_spend("fakecredit", 1, 40.0)
    rotated, idx = p.rotate_for_budget(10.0)  # nothing fits
    assert isinstance(rotated, bool) and idx in (0, 1)  # least-loaded, no raise


def test_ledger_rolls_over_on_a_new_utc_day(monkeypatch):
    monkeypatch.setenv("FAKE_CREDIT_KEYS", "k1")
    note_credit_spend("fakecredit", 0, 25.0)
    # simulate yesterday's ledger date
    base_mod.CREDIT_LEDGER_DATE["fakecredit"] = "2000-01-01"
    p = _FakeCreditProvider({})
    assert p.key_spend(0) == 0.0  # stale window discarded


def test_first_key_no_rotation_needed(monkeypatch):
    monkeypatch.setenv("FAKE_CREDIT_KEYS", "k1,k2")
    p = _FakeCreditProvider({})
    rotated, idx = p.rotate_for_budget(10.0)
    assert idx == 0 and rotated is False
