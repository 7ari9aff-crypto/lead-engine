"""Provider adapter base.

Every adapter implements: request(), and inherits error classification
plus Retry-After / x-ratelimit header parsing so the router reacts to real
signals instead of guessing.
"""
import json
import os
import random
import re
import string
import time as _time

import requests

from ..router import ProviderError, ProviderUnavailable, QuotaExhausted, RateLimited

RETRY_AFTER_KEYS = ("retry-after",)
REMAINING_KEYS = ("x-ratelimit-remaining-requests", "x-ratelimit-remaining",
                  "x-ratelimit-requests-remaining")


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
        self.api_key = os.environ.get(self.env_key) if self.env_key else None

    @property
    def available(self) -> bool:
        # env_key None => local provider (Ollama / SMTP), always "available"
        return self.env_key is None or bool(self.api_key)

    def request(self, task: str, payload: dict) -> dict:
        raise NotImplementedError

    # ------------------------------------------------------------------ http
    def _http(self, method: str, url: str, **kwargs):
        kwargs.setdefault("timeout", self.timeout)
        try:
            resp = requests.request(method, url, **kwargs)
        except requests.ConnectionError as exc:
            raise ProviderUnavailable(f"connection failed: {exc}") from exc
        except requests.Timeout as exc:
            raise ProviderUnavailable(f"timeout: {exc}") from exc
        if resp.status_code == 429:
            retry_after = resp.headers.get("retry-after")
            try:
                retry_after = float(retry_after) if retry_after else None
            except ValueError:
                retry_after = None
            raise RateLimited(f"{self.name}: 429 rate limited", retry_after=retry_after)
        if resp.status_code in (401, 403):
            raise ProviderUnavailable(f"{self.name}: auth rejected ({resp.status_code})")
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
