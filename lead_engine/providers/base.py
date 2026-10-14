"""Provider adapter base.

Every adapter implements: request(), and inherits error classification
plus Retry-After / x-ratelimit header parsing so the router reacts to real
signals instead of guessing.
"""
import json
import os
import random
import string

import requests

from ..router import (
    ProviderAuthError, ProviderError, ProviderUnavailable, QuotaExhausted, RateLimited,
)

RETRY_AFTER_KEYS = ("retry-after",)
REMAINING_KEYS = ("x-ratelimit-remaining-requests", "x-ratelimit-remaining",
                  "x-ratelimit-requests-remaining")

# ---------------------------------------------------------------- credit pool
# Per-provider, per-key index of credits already promised this UTC day.
# The adapters bump it AFTER a successful call returns the real cost (e.g.
# Manus usage events); the router consults it BEFORE the call and rotates
# the key first when the remaining budget approaches zero — a planned split
# mid-run, never an exception. Sources: MANUS_API_KEYS daily grants (300)
# minus this day's ledger catch.
CREDIT_SPEND: dict[str, list[float]] = {}
CREDIT_LEDGER_DATE: dict[str, str] = {}


def note_credit_spend(provider: str, key_index: int, cost: float) -> None:
    """Record `cost` credits against (provider, key_index) for today."""
    import datetime
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    per_provider = CREDIT_SPEND.setdefault(provider, [])
    while len(per_provider) <= key_index:
        per_provider.append(0.0)
    if CREDIT_LEDGER_DATE.get(provider) != today:
        CREDIT_LEDGER_DATE[provider] = today
        CREDIT_SPEND[provider] = [0.0] * max(len(per_provider), key_index + 1)
        per_provider = CREDIT_SPEND[provider]
        while len(per_provider) <= key_index:
            per_provider.append(0.0)
    per_provider[key_index] += float(cost or 0.0)


def random_local_part(length: int = 14) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


class BaseProvider:
    name = ""
    ptype = ""
    tasks = ()
    env_key = None

    def __init__(self, settings: dict):
        self.settings = settings or {}
        self.timeout = (self.settings.get("router", {}) or {}).get("timeout_seconds", 30)
        self._api_key = None
        self._key_index = 0
        self.endpoint_url = None
        self.configured_model_name = None
        self._session = None
        self._last_rate_info = {}

    def configure(self, provider_row: dict):
        """Apply non-secret settings from the provider registry for this call."""
        self.endpoint_url = provider_row.get("base_url") or None
        self.configured_model_name = provider_row.get("model_name") or None

    # ------------------------------------------------------------ key pool
    @property
    def api_key(self) -> str | None:
        if self._api_key is not None:
            return self._api_key
        return os.environ.get(self.env_key) if self.env_key else None

    @api_key.setter
    def api_key(self, value: str | None) -> None:
        self._api_key = value

    @property
    def keys(self) -> list:
        """Multiple keys per provider, comma-separated in the env var.
        The router rotates to the next key on 429/quota BEFORE switching
        provider — 5 Tavily keys means 5x the monthly credits."""
        return [k.strip() for k in (self.api_key or "").replace("\n", ",").split(",") if k.strip()]

    @property
    def available(self) -> bool:
        # env_key None => local provider (Ollama / SMTP), always "available"
        return self.env_key is None or bool(self.keys)

    def current_key(self):
        keys = self.keys
        if not keys:
            return None
        return keys[min(self._key_index, len(keys) - 1)]

    def rotate_key(self) -> bool:
        """Move to the next key. Returns False when the pool is exhausted."""
        if self._key_index < len(self.keys) - 1:
            self._key_index += 1
            return True
        return False

    def reset_keys(self) -> None:
        """Reset key index back to the first key."""
        self._key_index = 0

    def request(self, task: str, payload: dict) -> dict:
        raise NotImplementedError

    # -------------------------------------------------- credit-aware rotation
    def key_spend(self, key_index: int) -> float:
        """Credits already promised against the key at `key_index` today."""
        import datetime
        today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        per_provider = CREDIT_SPEND.get(self.name) or []
        if CREDIT_LEDGER_DATE.get(self.name) != today:
            return 0.0  # stale window: the day rolled over
        return float(per_provider[key_index]) if key_index < len(per_provider) else 0.0

    def budget_probe(self) -> float:
        """Plan-relevant cost estimate for ONE call of `task` — overridden by
        adapters with real metering; the default assumes one unit."""
        return 1.0

    def rotate_for_budget(self, planned_cost: float) -> tuple[bool, int]:
        """Move to the next key when the CURRENT one cannot fit `planned_cost`
        under its daily budget minus the safety margin. Returns
        (rotated?, key_index_used). Never raises and never runs out: a pool
        that is entirely over budget stays on the least-loaded key — the
        real 429/quota errors (if any) then drive the reactive rotation."""
        keys = self.keys
        if not keys:
            return False, self._key_index
        limit = self.daily_key_budget - self.key_budget_safety_margin
        fit_idx = None
        for offset in range(len(keys)):
            idx = (self._key_index + offset) % len(keys)
            if self.key_spend(idx) + planned_cost <= limit:
                fit_idx = idx
                break
        if fit_idx is None:
            # Everyone is full: least-loaded key + margin at the boundary is
            # the correct least-bad choice; the reactive layer owns errors.
            spends = [self.key_spend(i) for i in range(len(keys))]
            fit_idx = spends.index(min(spends))
        rotated = fit_idx != self._key_index
        self._key_index = fit_idx
        return rotated, fit_idx

    # ------------------------------------------------------------------ http
    def _http(self, method: str, url: str, **kwargs):
        kwargs.setdefault("timeout", self.timeout)
        if self._session is None:
            self._session = requests.Session()
        try:
            resp = self._session.request(method, url, **kwargs)
        except requests.ConnectionError as exc:
            raise ProviderUnavailable(f"connection failed: {exc}") from exc
        except requests.Timeout as exc:
            raise ProviderUnavailable(f"timeout: {exc}") from exc
        self._last_rate_info = self._rate_info(resp.headers)
        if resp.status_code == 429:
            retry_after = resp.headers.get("retry-after")
            try:
                retry_after = float(retry_after) if retry_after else None
            except ValueError:
                retry_after = None
            raise RateLimited(f"{self.name}: 429 rate limited", retry_after=retry_after)
        if resp.status_code in (401, 403):
            raise ProviderAuthError(f"{self.name}: auth rejected ({resp.status_code})")
        if resp.status_code in (402,):
            raise QuotaExhausted(f"{self.name}: payment required")
        if resp.status_code >= 500:
            raise ProviderUnavailable(f"{self.name}: server error {resp.status_code}")
        if resp.status_code >= 400:
            body = resp.text[:300]
            low = body.lower()
            if "quota" in low or "credit" in low:
                raise QuotaExhausted(f"{self.name}: {body}")
            raise ProviderError(f"{self.name}: HTTP {resp.status_code}: {body}")
        return resp

    def _rate_info(self, headers) -> dict:
        info = {}
        for key in REMAINING_KEYS:
            if key in headers:
                try:
                    info["remaining_requests"] = int(float(headers[key]))
                except (TypeError, ValueError):
                    pass
                break
        for key in ("x-ratelimit-remaining-tokens",):
            if key in headers:
                try:
                    info["remaining_tokens"] = int(float(headers[key]))
                except (TypeError, ValueError):
                    pass
        return info

    @staticmethod
    def _json(resp):
        try:
            return resp.json()
        except json.JSONDecodeError as exc:
            raise ProviderError(f"invalid JSON from provider: {exc}") from exc
