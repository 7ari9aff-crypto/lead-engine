"""ManusDiscovery: the resumable engine behind the async discovery stage.

No network, no database: a scripted fake client stands in for Manus so the
tests can pin the money-sensitive behavior (never pay twice, never overspend a
key, never block on a slow task) deterministically.
"""
from __future__ import annotations

import json

import pytest


from infrastructure.providers.manus import (
    KeyLedger,
    ManusError,
    TaskDetail,
)
from infrastructure.providers.manus_engine import (
    ManusDiscovery,
    build_prompt,
)

ICP = {"industry": "dental", "country": "SA",
       "cities": [{"name": "Jeddah", "ar": "جدة"}, "Riyadh"],
       "keywords_en": ["private dental clinic"], "keywords_ar": ["عيادة أسنان"]}


class FakeClient:
    """Scripted Manus. ``script[task_id]`` = list of TaskDetail returned in turn."""

    def __init__(self, key: str, world: "World"):
        self.key, self.world = key, world

    def create_task(self, prompt: str) -> str:
        if self.world.create_error:
            raise self.world.create_error
        tid = f"T{len(self.world.created) + 1}"
        self.world.created.append((tid, self.key, prompt))
        return tid

    def task_detail(self, task_id: str) -> TaskDetail:
        seq = self.world.script.get(task_id) or [TaskDetail("stopped", 10)]
        return seq.pop(0) if len(seq) > 1 else seq[0]

    def final_answer(self, task_id: str) -> str:
        return self.world.answers.get(task_id, "[]")


class World:
    def __init__(self):
        self.created: list[tuple[str, str, str]] = []
        self.script: dict[str, list[TaskDetail]] = {}
        self.answers: dict[str, str] = {}
        self.create_error: Exception | None = None

    def factory(self, key: str) -> FakeClient:
        return FakeClient(key, self)


def _engine(world, keys=("k1", "k2"), balances=None, state=None, **kw):
    ledger = KeyLedger(list(keys), balances=balances or {"k1": 300, "k2": 300})
    return ManusDiscovery(ledger=ledger, client_factory=world.factory, state=state, **kw)


def _answer(*names):
    return json.dumps([{"name": n, "website": f"https://{n.lower()}.sa"} for n in names])


# ------------------------------------------------------------------ prompt
def test_prompt_is_generic_and_carries_the_icp():
    p = build_prompt(ICP, city="Jeddah", count=15)
    assert "Jeddah" in p and "جدة" in p and "dental" in p
    assert "15" in p and "JSON" in p
    assert "do not invent" in p.lower() or "لا تخترع" in p


def test_prompt_has_no_hardcoded_sector():
    other = {**ICP, "industry": "law firms", "keywords_en": ["corporate law firm"],
             "keywords_ar": []}
    p = build_prompt(other, city="Cairo", count=10)
    assert "law firms" in p and "dental" not in p.lower() and "clinic" not in p.lower()


# -------------------------------------------------------------- submission
def test_one_task_per_city_is_submitted_with_the_best_key():
    world = World()
    eng = _engine(world, balances={"k1": 100, "k2": 1300})
    eng.submit(ICP, per_city=15)
    assert len(world.created) == 2                       # Jeddah + Riyadh
    assert {k for _, k, _ in world.created} == {"k2", "k1"} or world.created[0][1] == "k2"
    assert world.created[0][1] == "k2"                   # richest key first


def test_submission_is_idempotent_across_restarts():
    """The core money rule: restoring state must NOT create the tasks again."""
    world = World()
    eng = _engine(world)
    eng.submit(ICP, per_city=15)
    saved = eng.state()
    assert len(world.created) == 2

    revived = _engine(world, state=saved)
    revived.submit(ICP, per_city=15)
    assert len(world.created) == 2                       # still 2, nothing re-paid


def test_no_key_with_enough_credit_stops_submission_without_losing_state():
    world = World()
    eng = _engine(world, balances={"k1": 40, "k2": 35}, estimate=20)   # 40-20 < floor
    eng.submit(ICP, per_city=15)
    assert world.created == []
    assert eng.state()["unsubmitted"] == ["Jeddah", "Riyadh"]
    assert eng.exhausted is True


def test_rate_limited_key_is_skipped_and_task_goes_to_the_next_key():
    world = World()
    calls = {"n": 0}
    real = world.factory

    def factory(key):
        client = real(key)
        orig = client.create_task

        def create(prompt, orig=orig, key=key):
            calls["n"] += 1
            if key == "k1":
                raise ManusError("RATE_LIMIT", "429")
            return orig(prompt)
        client.create_task = create
        return client

    ledger = KeyLedger(["k1", "k2"], balances={"k1": 1300, "k2": 300})
    eng = ManusDiscovery(ledger=ledger, client_factory=factory)
    eng.submit({**ICP, "cities": ["Jeddah"]}, per_city=15)
    assert [k for _, k, _ in world.created] == ["k2"]


def test_auth_failure_retires_that_key_for_the_run():
    world = World()
    real = world.factory

    def factory(key):
        c = real(key)
        if key == "k1":
            c.create_task = lambda prompt: (_ for _ in ()).throw(ManusError("AUTH", "401"))
        return c

    ledger = KeyLedger(["k1", "k2"], balances={"k1": 1300, "k2": 300})
    eng = ManusDiscovery(ledger=ledger, client_factory=factory)
    eng.submit({**ICP, "cities": ["A", "B"]}, per_city=5)
    assert all(k == "k2" for _, k, _ in world.created)
    assert eng.state()["retired_keys"] == [0]            # by position, never value


# ----------------------------------------------------------------- polling
def test_poll_collects_finished_tasks_and_settles_credit():
    world = World()
    eng = _engine(world, balances={"k1": 300, "k2": 100})
    eng.submit({**ICP, "cities": ["Jeddah"]}, per_city=15)
    [(tid, key, _)] = world.created
    world.script[tid] = [TaskDetail("stopped", 48)]
    world.answers[tid] = _answer("Alpha", "Beta")

    done = eng.poll()
    assert [c["name"] for c in done.companies] == ["Alpha", "Beta"]
    assert eng.ledger.balances[key] == (300 if key == "k1" else 100) - 48
    assert eng.pending == 0 and done.finished


def test_poll_leaves_running_tasks_pending_without_blocking():
    world = World()
    eng = _engine(world)
    eng.submit({**ICP, "cities": ["Jeddah"]}, per_city=15)
    [(tid, _, _)] = world.created
    world.script[tid] = [TaskDetail("running", 5)]
    done = eng.poll()
    assert done.companies == [] and eng.pending == 1 and not done.finished


def test_a_finished_task_is_collected_only_once():
    world = World()
    eng = _engine(world)
    eng.submit({**ICP, "cities": ["Jeddah"]}, per_city=15)
    [(tid, _, _)] = world.created
    world.script[tid] = [TaskDetail("stopped", 20)]
    world.answers[tid] = _answer("Alpha")
    assert len(eng.poll().companies) == 1
    assert eng.poll().companies == []                    # not double counted


def test_failed_task_is_recorded_and_still_charges_what_it_used():
    world = World()
    eng = _engine(world, balances={"k1": 300, "k2": 100})
    eng.submit({**ICP, "cities": ["Jeddah"]}, per_city=15)
    [(tid, key, _)] = world.created
    world.script[tid] = [TaskDetail("error", 7)]
    done = eng.poll()
    assert done.failed == 1 and done.companies == []
    assert eng.ledger.balances[key] == (300 if key == "k1" else 100) - 7


def test_stuck_task_is_abandoned_after_the_deadline():
    world = World()
    clock = {"t": 1000.0}
    eng = _engine(world, task_timeout_s=600, now=lambda: clock["t"])
    eng.submit({**ICP, "cities": ["Jeddah"]}, per_city=15)
    [(tid, _, _)] = world.created
    world.script[tid] = [TaskDetail("running", 5)]
    clock["t"] += 601
    done = eng.poll()
    assert done.timed_out == 1 and eng.pending == 0


def test_transient_poll_error_keeps_the_task_for_next_time():
    world = World()
    eng = _engine(world)
    eng.submit({**ICP, "cities": ["Jeddah"]}, per_city=15)
    [(tid, key, _)] = world.created
    real = world.factory

    def flaky(k):
        c = real(k)
        c.task_detail = lambda t: (_ for _ in ()).throw(ManusError("TRANSIENT", "boom"))
        return c

    eng._client_factory = flaky
    done = eng.poll()
    assert eng.pending == 1 and done.companies == []


# ------------------------------------------------------------------- state
def test_state_roundtrip_contains_no_key_values():
    world = World()
    eng = _engine(world, keys=("secret-AAA", "secret-BBB"),
                  balances={"secret-AAA": 300, "secret-BBB": 300})
    eng.submit({**ICP, "cities": ["Jeddah"]}, per_city=15)
    assert "secret-" not in json.dumps(eng.state())


def test_restored_engine_polls_tasks_submitted_before_the_restart():
    world = World()
    eng = _engine(world)
    eng.submit({**ICP, "cities": ["Jeddah"]}, per_city=15)
    [(tid, _, _)] = world.created
    saved = json.loads(json.dumps(eng.state()))          # must survive JSON (checkpoint)
    world.script[tid] = [TaskDetail("stopped", 30)]
    world.answers[tid] = _answer("Alpha")

    revived = _engine(world, state=saved)
    assert [c["name"] for c in revived.poll().companies] == ["Alpha"]


# ------------------------------------------------------- production wiring
def test_build_stage_reads_the_key_pool_lazily(monkeypatch):
    from infrastructure.providers.manus_engine import build_manus_stage

    monkeypatch.delenv("MANUS_API_KEY", raising=False)
    cfg = build_manus_stage()                       # built before keys exist (boot order)
    with pytest.raises(RuntimeError):
        cfg.ledger_factory(None)

    monkeypatch.setenv("MANUS_API_KEY", "k1, k2\nk3,,")   # hydrated after boot
    ledger = cfg.ledger_factory(None)
    assert ledger.keys == ["k1", "k2", "k3"]


def test_build_stage_restores_balances_by_position(monkeypatch):
    from infrastructure.providers.manus_engine import build_manus_stage

    monkeypatch.setenv("MANUS_API_KEY", "k1,k2")
    cfg = build_manus_stage()
    ledger = cfg.ledger_factory({"0": 31.0, "1": 1300.0})
    assert ledger.balances == {"k1": 31.0, "k2": 1300.0}
