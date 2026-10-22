"""Resumable Manus discovery engine (ADR-0011).

One research task per city of the ICP. The engine never blocks: ``submit``
creates the tasks it can afford, ``poll`` collects whatever has finished, and
``state()`` is a JSON-safe snapshot the job stores in its checkpoint, so a
restarted worker carries on without paying for a task twice.

Money rules (each one has a test):
* a task already submitted is never submitted again after a restart;
* a key is only used if it can pay the estimate and stay above the floor;
* a rate-limited key is skipped for that task, a rejected (AUTH) key is retired;
* a finished or failed task is charged what Manus reports it used;
* a task that never finishes is abandoned after a deadline.

The prompt is built only from the ICP (industry, cities, keywords): nothing
here knows what sector is being searched.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from infrastructure.providers.manus import (
    KeyLedger,
    ManusError,
    parse_companies,
)

DEFAULT_ESTIMATE = 60          # credits held per task while it runs (15 leads ~ 48)
DEFAULT_TASK_TIMEOUT_S = 25 * 60


def _city_names(city: Any) -> tuple[str, str]:
    if isinstance(city, dict):
        name = str(city.get("name") or "")
        return name, str(city.get("ar") or name)
    return str(city), str(city)


def build_prompt(icp: dict[str, Any], *, city: str, count: int) -> str:
    """A sector-agnostic research brief built from the ICP."""
    match = next((c for c in icp.get("cities", []) if _city_names(c)[0] == city), city)
    en, ar = _city_names(match)
    industry = icp.get("industry") or "businesses"
    keywords = ", ".join([*icp.get("keywords_en", []), *icp.get("keywords_ar", [])])
    country = icp.get("country") or ""
    where = f"{en} ({ar})" if ar and ar != en else en
    return (
        f"Search the web for {count} different real {industry} businesses in {where}"
        f"{', ' + country if country else ''}."
        f"{' Useful search terms: ' + keywords + '.' if keywords else ''} "
        "Only independent businesses with their own website. For each one give: "
        "name, website, phone, email (only if published publicly on its own site), "
        "instagram (if any), and source (the URL you took the information from). "
        "Leave any field empty instead of guessing: do not invent values. "
        "Output a JSON array only, with no explanation."
    )


@dataclass
class PollResult:
    companies: list[dict[str, Any]] = field(default_factory=list)
    failed: int = 0
    timed_out: int = 0
    finished: bool = False


class ManusDiscovery:
    def __init__(self, *, ledger: KeyLedger, client_factory: Callable[[str], Any],
                 state: dict[str, Any] | None = None, estimate: float = DEFAULT_ESTIMATE,
                 task_timeout_s: float = DEFAULT_TASK_TIMEOUT_S,
                 now: Callable[[], float] = time.time):
        self.ledger = ledger
        self._client_factory = client_factory
        self._estimate = estimate
        self._timeout = task_timeout_s
        self._now = now
        state = state or {}
        # tasks: {task_id: {"city", "key", "at"}}  (key = POSITION in ledger.keys)
        self._tasks: dict[str, dict[str, Any]] = dict(state.get("tasks", {}))
        self._submitted: list[str] = list(state.get("submitted", []))
        self._unsubmitted: list[str] = list(state.get("unsubmitted", []))
        self._retired: set[int] = set(state.get("retired_keys", []))
        self._collected: set[str] = set(state.get("collected", []))
        self._failed = int(state.get("failed", 0))
        self._timed_out = int(state.get("timed_out", 0))
        if "ledger" in state:
            self.ledger = KeyLedger.restore(ledger.keys, state["ledger"], floor=ledger.floor)
        for tid, t in self._tasks.items():          # re-hold credit for tasks in flight
            self.ledger._held[self.ledger.keys[t["key"]]] += self._estimate

    # ------------------------------------------------------------------ state
    @property
    def pending(self) -> int:
        return len(self._tasks)

    @property
    def exhausted(self) -> bool:
        """Work remains but no key can pay for another task. Uses the exact
        rule ``_reserve`` applies, so 'exhausted' can never disagree with
        'cannot submit' (that mismatch would park the job forever)."""
        return bool(self._unsubmitted) and not self._affordable()

    def _affordable(self) -> list[str]:
        return [k for k in self.ledger.keys
                if self.ledger.keys.index(k) not in self._retired
                and self.ledger.balances[k] - self.ledger._held[k] - self._estimate
                >= self.ledger.floor]

    def state(self) -> dict[str, Any]:
        return {
            "tasks": self._tasks, "submitted": self._submitted,
            "unsubmitted": self._unsubmitted, "retired_keys": sorted(self._retired),
            "collected": sorted(self._collected), "ledger": self.ledger.snapshot(),
            "failed": self._failed, "timed_out": self._timed_out,
        }

    # ---------------------------------------------------------------- submit
    def submit(self, icp: dict[str, Any], *, per_city: int) -> None:
        if not self._submitted and not self._unsubmitted:
            self._unsubmitted = [_city_names(c)[0] for c in icp.get("cities", [])]
        for city in list(self._unsubmitted):
            if not self._submit_one(icp, city, per_city):
                break

    def _submit_one(self, icp: dict[str, Any], city: str, per_city: int) -> bool:
        tried: set[str] = set()
        while True:
            key = self._reserve(tried)
            if key is None:
                return False
            try:
                task_id = self._client_factory(key).create_task(
                    build_prompt(icp, city=city, count=per_city))
            except ManusError as exc:
                self.ledger.release(key, self._estimate)
                if exc.kind == "AUTH":
                    self._retired.add(self.ledger.keys.index(key))
                elif exc.kind == "CAPACITY":
                    self.ledger.balances[key] = 0.0
                tried.add(key)               # RATE_LIMIT / TRANSIENT: next key, this task
                continue
            self._tasks[task_id] = {"city": city, "key": self.ledger.keys.index(key),
                                    "at": self._now()}
            self._submitted.append(city)
            self._unsubmitted.remove(city)
            return True

    def _reserve(self, tried: set[str]) -> str | None:
        usable = [k for k in self._affordable() if k not in tried]
        if not usable:
            return None
        best = max(usable, key=lambda k: self.ledger.balances[k] - self.ledger._held[k])
        self.ledger._held[best] += self._estimate
        return best

    # ------------------------------------------------------------------ poll
    def poll(self) -> PollResult:
        result = PollResult()
        for task_id in list(self._tasks):
            info = self._tasks[task_id]
            key = self.ledger.keys[info["key"]]
            client = self._client_factory(key)
            try:
                detail = client.task_detail(task_id)
            except ManusError:
                if self._now() - info["at"] > self._timeout:
                    self._abandon(task_id, key, result)
                continue                              # keep it; try again next poll
            if not detail.finished:
                if self._now() - info["at"] > self._timeout:
                    self.ledger.settle(key, self._estimate, detail.credits)
                    self._abandon(task_id, key, result, charged=True)
                continue
            self.ledger.settle(key, self._estimate, detail.credits)
            del self._tasks[task_id]
            self._collected.add(task_id)
            if detail.failed:
                self._failed += 1
                result.failed += 1
                continue
            try:
                answer = client.final_answer(task_id)
            except ManusError:
                self._failed += 1
                result.failed += 1
                continue
            for company in parse_companies(answer):
                company["city"] = info["city"]
                result.companies.append(company)
        result.finished = not self._tasks and not self._unsubmitted
        return result

    def _abandon(self, task_id: str, key: str, result: PollResult, charged: bool = False) -> None:
        if not charged:
            self.ledger.release(key, self._estimate)
        del self._tasks[task_id]
        self._timed_out += 1
        result.timed_out += 1


def build_manus_stage():
    """Production wiring for the Manus stage, or ``None`` when no key exists.

    The key pool is read lazily from ``MANUS_API_KEY`` (comma/newline separated)
    each time the stage runs, so keys hydrated from the credential store after
    boot are still seen. Returns a ``ManusStageConfig``-compatible object."""
    import os
    import re

    import httpx

    from application.handlers.manus_stage import ManusStageConfig
    from infrastructure.providers.manus import KeyLedger, ManusClient

    def keys() -> list[str]:
        raw = os.environ.get("MANUS_API_KEY", "")
        return [k.strip() for k in re.split(r"[,\n]", raw) if k.strip()]

    def ledger_factory(snapshot):
        pool = keys()
        if not pool:
            raise RuntimeError("MANUS_API_KEY is not set")
        return KeyLedger.restore(pool, snapshot) if snapshot else KeyLedger(pool)

    def fetch(url: str) -> str | None:
        try:
            resp = httpx.get(url, timeout=12, follow_redirects=True,
                             headers={"User-Agent": "Mozilla/5.0 (compatible; LeadEngineVerifier)"})
        except httpx.HTTPError:
            return None
        return resp.text if resp.status_code == 200 else None

    return ManusStageConfig(ledger_factory=ledger_factory,
                            client_factory=lambda key: ManusClient(key), fetch=fetch)
