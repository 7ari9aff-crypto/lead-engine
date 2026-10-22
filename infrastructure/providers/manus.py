"""Manus async discovery building blocks (ADR-0011).

Manus is a long-running research agent: one task takes minutes and is metered
in credits. It is therefore NOT a synchronous ``search_companies`` adapter (that
would hold a Postgres transaction open for the whole task). These pieces are
used by an asynchronous discovery stage that keeps its state in the job
checkpoint so it survives worker restarts without paying twice.

* ``KeyLedger``    credit-aware choice among many keys (no balance endpoint
                   exists, so we track spend from each task's ``credit_usage``).
* ``ManusClient``  the four HTTP calls we need, with failures classified.
* ``parse_companies``  honest parsing of the agent's JSON answer.
* ``verify_company``   nothing Manus claims is trusted until the company's own
                   page confirms it.

Secrets: key values live only in memory; ``KeyLedger.snapshot`` is keyed by
position, never by value, so it is safe to put in a checkpoint or a log.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlparse

import httpx

BASE_URL = "https://api.manus.ai"
_TIMEOUT = httpx.Timeout(30.0)

DEFAULT_FLOOR = 30          # owner rule: switch key when ~30 credits are left
DEFAULT_BALANCE = 300       # conservative assumption for a key never measured


# --------------------------------------------------------------------- ledger
class KeyLedger:
    """Tracks the estimated remaining credits of each key.

    Choice rule: highest remaining balance first, never a key at or under
    ``floor``. ``reserve`` holds an estimate while a task is in flight so that
    several concurrent tasks cannot all land on the same nearly-empty key.
    """

    def __init__(self, keys: list[str], balances: dict[str, float] | None = None,
                 floor: int = DEFAULT_FLOOR, default_balance: int = DEFAULT_BALANCE):
        self.keys = list(keys)
        self.floor = floor
        self.balances: dict[str, float] = {
            k: float((balances or {}).get(k, default_balance)) for k in self.keys}
        self._held: dict[str, float] = {k: 0.0 for k in self.keys}

    def _available(self, key: str) -> float:
        return self.balances[key] - self._held[key]

    def pick(self) -> str | None:
        usable = [k for k in self.keys if self._available(k) > self.floor]
        return max(usable, key=self._available) if usable else None

    def reserve(self, estimate: float) -> str | None:
        """Choose a key that can pay ``estimate`` and still stay above floor."""
        usable = [k for k in self.keys if self._available(k) - estimate >= self.floor]
        if not usable:
            return None
        key = max(usable, key=self._available)
        self._held[key] += estimate
        return key

    def release(self, key: str, estimate: float) -> None:
        self._held[key] = max(0.0, self._held[key] - estimate)

    def charge(self, key: str, credits: float) -> None:
        self.balances[key] = max(0.0, self.balances[key] - credits)

    def settle(self, key: str, estimate: float, actual: float) -> None:
        """A task finished: drop the hold, book the real cost."""
        self.release(key, estimate)
        self.charge(key, actual)

    # -- persistence ----------------------------------------------------------
    def snapshot(self) -> dict[str, float]:
        """Balances by key POSITION (``"0"``, ``"1"``...), never by key value."""
        return {str(i): round(self.balances[k], 2) for i, k in enumerate(self.keys)}

    @classmethod
    def restore(cls, keys: list[str], snap: dict[str, float] | None,
                floor: int = DEFAULT_FLOOR) -> "KeyLedger":
        snap = snap or {}
        balances = {k: float(snap[str(i)]) for i, k in enumerate(keys) if str(i) in snap}
        return cls(keys, balances=balances, floor=floor)


# --------------------------------------------------------------------- client
class ManusError(RuntimeError):
    """A Manus call failed. ``kind`` mirrors the gateway FailureClass names."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


def _kind_for_status(code: int) -> str:
    if code in (401, 403):
        return "AUTH"
    if code == 429:
        return "RATE_LIMIT"
    if code in (402,):
        return "CAPACITY"
    if code >= 500:
        return "TRANSIENT"
    return "VALIDATION"


@dataclass(frozen=True)
class TaskDetail:
    status: str
    credits: float

    @property
    def failed(self) -> bool:
        return self.status in ("error", "failed")

    @property
    def finished(self) -> bool:
        return self.status in ("stopped", "completed", "error", "failed")


class ManusClient:
    def __init__(self, api_key: str, *, base_url: str = BASE_URL,
                 transport: httpx.BaseTransport | None = None):
        self._key = api_key
        self._base = base_url.rstrip("/")
        self._transport = transport

    def _request(self, method: str, path: str, *, json_body: dict | None = None,
                 params: dict | None = None) -> dict[str, Any]:
        try:
            with httpx.Client(timeout=_TIMEOUT, transport=self._transport) as client:
                resp = client.request(
                    method, self._base + path, json=json_body, params=params,
                    headers={"x-manus-api-key": self._key, "User-Agent": "curl/8"})
        except httpx.HTTPError as exc:
            raise ManusError("TRANSIENT", type(exc).__name__) from exc
        if resp.status_code >= 400:
            raise ManusError(_kind_for_status(resp.status_code), f"HTTP {resp.status_code}")
        data = resp.json()
        if data.get("ok") is False:
            code = json.dumps(data.get("error") or "").lower()
            kind = "CAPACITY" if ("credit" in code or "quota" in code or "balance" in code) \
                else "VALIDATION"
            raise ManusError(kind, code[:120] or "manus returned ok=false")
        return data

    def create_task(self, prompt: str) -> str:
        data = self._request("POST", "/v2/task.create", json_body={
            "message": {"content": prompt}, "hide_in_task_list": True})
        return str(data["task_id"])

    def task_detail(self, task_id: str) -> TaskDetail:
        task = self._request("GET", "/v2/task.detail", params={"task_id": task_id})["task"]
        return TaskDetail(status=str(task.get("status", "")),
                          credits=float(task.get("credit_usage") or 0))

    def final_answer(self, task_id: str) -> str:
        """The newest assistant message (the API lists newest first)."""
        data = self._request("GET", "/v2/task.listMessages",
                             params={"task_id": task_id, "order": "desc", "limit": 20})
        for message in data.get("messages", []):
            if message.get("type") == "assistant_message":
                return str((message.get("assistant_message") or {}).get("content") or "")
        return ""


# -------------------------------------------------------------------- parsing
def _domain(url: str) -> str:
    host = urlparse(url if "//" in url else "//" + url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _clean(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def parse_companies(text: str) -> list[dict[str, Any]]:
    """Extract companies from the agent's answer.

    Tolerates a markdown fence or surrounding prose. Never raises: an answer we
    cannot read is an empty result, and the caller records that honestly.
    Rows without a name and a website are dropped; duplicates by domain merge.
    """
    if not text:
        return []
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end <= start:
        return []
    try:
        rows = json.loads(text[start:end + 1])
    except (ValueError, TypeError):
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        name, website = _clean(row.get("name")), _clean(row.get("website"))
        if not name or not website:
            continue
        domain = _domain(website)
        if not domain or domain in seen:
            continue
        seen.add(domain)
        out.append({
            "name": name, "website": website, "phone": _clean(row.get("phone")),
            "email": _clean(row.get("email")),
            "instagram": _clean(row.get("instagram")),
            "source": _clean(row.get("source")),
        })
    return out


# --------------------------------------------------------------- verification
_TAG_RE = re.compile(r"<[^>]+>")
_CONTACT_PATHS = ("", "/contact", "/contact-us", "/en/contact", "/ar/contact", "/about")


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _phone_variants(phone: str) -> set[str]:
    """Match +966501112222 and 0501112222 as the same number."""
    d = _digits(phone)
    if len(d) < 8:
        return set()
    variants = {d, d[-9:]}
    if d.startswith("966"):
        variants.add("0" + d[3:])
    return {v for v in variants if len(v) >= 8}


def verify_company(company: dict[str, Any], *, fetch: Callable[[str], str | None]) -> dict[str, Any]:
    """Confirm claimed contacts on the company's OWN website.

    ``fetch(url)`` returns page HTML or ``None``. A phone or email that does not
    appear on the site is removed (not kept as 'probably right'); an
    unreachable site verifies nothing.
    """
    base = company["website"].rstrip("/")
    pages: list[str] = []
    for path in _CONTACT_PATHS:
        html = fetch(base + path)
        if html:
            pages.append(html)
        if path == "" and not html:
            break                      # homepage unreachable: do not probe further
    haystack = " ".join(pages)
    text = _TAG_RE.sub(" ", haystack)
    digits_only = _digits(text)

    out = {**company, "site_reachable": bool(pages),
           "phone_verified": False, "email_verified": False}

    phone = company.get("phone")
    if phone and pages:
        if any(v in digits_only for v in _phone_variants(phone)):
            out["phone_verified"] = True
            out["phone"] = "+" + _digits(phone) if str(phone).strip().startswith("+") \
                else _digits(phone)
    if not out["phone_verified"]:
        out["phone"] = None

    email = (company.get("email") or "").lower()
    if email and pages and email in haystack.lower():
        out["email_verified"] = True
        out["email"] = email
    if not out["email_verified"]:
        out["email"] = None
    return out
