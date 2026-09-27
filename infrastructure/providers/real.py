"""Real vendor adapters — same capability contract as the fakes (ADR-0009).

Request formats mirror the legacy stack (lead_engine/providers/search.py).
Legacy multi-key pools are honored: comma/newline separated env values rotate
on AUTH / RATE_LIMIT before the waterfall moves to the next vendor.
"""
from __future__ import annotations

import os
import random
import smtplib
import socket
from typing import Any

import httpx
from dns import resolver as dns_resolver

from contracts.providers import Capability, ProviderResult, ProviderSpec

_TIMEOUT = httpx.Timeout(25.0)


class KeyPool:
    """Legacy-compatible multi-key pool from one env var."""

    def __init__(self, env_name: str):
        raw = (os.environ.get(env_name) or "").replace("\n", ",")
        self.keys = [k.strip() for k in raw.split(",") if k.strip()]
        self._index = 0

    def current(self) -> str | None:
        if not self.keys:
            return None
        return self.keys[min(self._index, len(self.keys) - 1)]

    def rotate(self) -> bool:
        if self._index < len(self.keys) - 1:
            self._index += 1
            return True
        return False

    def __len__(self) -> int:
        return len(self.keys)


class TavilySearchAdapter:
    spec = ProviderSpec(provider_id="tavily", capability=Capability.SEARCH_COMPANIES,
                        priority=10, cost_cents_per_call=0)

    def __init__(self):
        self.pool = KeyPool("TAVILY_API_KEY")

    def call(self, operation: str, params: dict[str, Any]) -> ProviderResult:
        if not len(self.pool):
            return ProviderResult(ok=False, error="TAVILY_API_KEY missing")
        while True:
            body = {
                "api_key": self.pool.current(),
                "query": params["query"],
                "search_depth": "basic",
                "max_results": int(params.get("max_results", 6)),
            }
            try:
                with httpx.Client(timeout=_TIMEOUT) as client:
                    resp = client.post("https://api.tavily.com/search", json=body)
                    resp.raise_for_status()
                    data = resp.json()
                results = [{"title": r.get("title", ""), "url": r.get("url", ""),
                            "snippet": r.get("content", "")}
                           for r in data.get("results", [])]
                return ProviderResult(ok=True, data={"results": results, "provider": "tavily"})
            except httpx.HTTPStatusError as exc:
                code = exc.response.status_code
                if code in (401, 403, 429) and self.pool.rotate():
                    continue
                raise


class ExaSearchAdapter:
    spec = ProviderSpec(provider_id="exa", capability=Capability.SEARCH_COMPANIES,
                        priority=20, cost_cents_per_call=0)

    def __init__(self):
        self.pool = KeyPool("EXA_API_KEY")

    def call(self, operation: str, params: dict[str, Any]) -> ProviderResult:
        if not len(self.pool):
            return ProviderResult(ok=False, error="EXA_API_KEY missing")
        while True:
            body = {"query": params["query"],
                    "numResults": int(params.get("max_results", 6)),
                    "type": "auto", "contents": {"text": {"maxCharacters": 400}}}
            try:
                with httpx.Client(timeout=_TIMEOUT) as client:
                    resp = client.post("https://api.exa.ai/search", json=body,
                                       headers={"x-api-key": self.pool.current()})
                    resp.raise_for_status()
                    data = resp.json()
                results = [{"title": r.get("title", ""), "url": r.get("url", ""),
                            "snippet": (r.get("text") or "")[:400]}
                           for r in data.get("results", [])]
                return ProviderResult(ok=True, data={"results": results, "provider": "exa"})
            except httpx.HTTPStatusError as exc:
                code = exc.response.status_code
                if code in (401, 403, 429) and self.pool.rotate():
                    continue
                raise


class SmtpVerifyAdapter:
    """Real mailbox probing: MX lookup + RCPT TO, with catch-all detection.
    Honest statuses only — network-blocked environments yield UNKNOWN."""

    spec = ProviderSpec(provider_id="smtp-verify", capability=Capability.VERIFY_EMAIL,
                        priority=10, supports_idempotency=True)

    def call(self, operation: str, params: dict[str, Any]) -> ProviderResult:
        email = str(params.get("email", ""))
        local, _, domain = email.partition("@")
        if not domain:
            return ProviderResult(ok=True, data={"status": "INVALID",
                                                 "provider_verified": True})
        try:
            mx = dns_resolver.resolve(domain, "MX")
            host = str(sorted(mx, key=lambda r: r.preference)[0].exchange).rstrip(".")
        except Exception:  # noqa: BLE001 — no MX / resolver failure
            return ProviderResult(ok=True, data={"status": "UNKNOWN",
                                                 "provider_verified": False})

        verdict = self._rcpt(host, email)
        if verdict == "accepted":
            random_probe = self._rcpt(
                host, f"probe-{random.randint(10**8, 10**9 - 1)}@{domain}")
            status = "CATCH_ALL" if random_probe == "accepted" else "DELIVERABLE"
            evidence = {"smtp_accepted": random_probe != "accepted",
                        "provider_verified": True}
        elif verdict == "rejected":
            status, evidence = "INVALID", {"provider_verified": True}
        else:
            status, evidence = "UNKNOWN", {"provider_verified": False}
        return ProviderResult(ok=True, data={"status": status, **evidence})

    @staticmethod
    def _rcpt(host: str, email: str) -> str:
        try:
            with smtplib.SMTP(host, 25, timeout=12) as smtp:
                smtp.ehlo("lead-engine-v6")
                smtp.mail("verify@lead-engine.local")
                code, _ = smtp.rcpt(email)
                if 200 <= code <= 251:
                    return "accepted"
                if code in (550, 551, 553):
                    return "rejected"
                return "ambiguous"
        except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError,
                socket.timeout, OSError):
            return "unreachable"


class GeminiReasonModel:
    """Model adapter for the reasoning capability via Gemini."""

    def __init__(self, model_id: str = "gemini-2.0-flash"):
        self.model_id = model_id
        self.pool = KeyPool("GEMINI_API_KEY")

    def complete(self, capability: str, prompt: str, params: dict[str, Any]) -> Any:
        if not len(self.pool):
            raise RuntimeError("GEMINI_API_KEY missing")
        while True:
            url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
                   f"{self.model_id}:generateContent?key={self.pool.current()}")
            try:
                with httpx.Client(timeout=_TIMEOUT) as client:
                    resp = client.post(url,
                                       json={"contents": [{"parts": [{"text": prompt}]}]})
                    resp.raise_for_status()
                    data = resp.json()
                break
            except httpx.HTTPStatusError as exc:
                code = exc.response.status_code
                if code in (401, 403, 429) and self.pool.rotate():
                    continue
                raise
        from infrastructure.models.gateway import ModelReply

        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return ModelReply(text=text, model_id=self.model_id, cost_cents=0,
                          tokens=int(data.get("usageMetadata", {})
                                     .get("totalTokenCount", 0)))
