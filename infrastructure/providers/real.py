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


class ApolloContactAdapter:
    """FIND_CONTACT via Apollo people search (0 credits on paid plans).
    Request/response shape mirrors the proven legacy adapter."""

    spec = ProviderSpec(provider_id="apollo", capability=Capability.FIND_CONTACT,
                        priority=10, cost_cents_per_call=0)

    def __init__(self):
        self.pool = KeyPool("APOLLO_API_KEY")

    def call(self, operation: str, params: dict[str, Any]) -> ProviderResult:
        if not len(self.pool):
            return ProviderResult(ok=False, error="APOLLO_API_KEY missing")
        while True:
            try:
                with httpx.Client(timeout=_TIMEOUT) as client:
                    resp = client.post(
                        "https://api.apollo.io/v1/mixed_people/search",
                        json={"organization_domains": [params.get("domain")] if params.get("domain") else [],
                               "person_titles": params.get("titles", []),
                               "page": 1},
                        headers={"X-Api-Key": self.pool.current(),
                                  "Content-Type": "application/json"})
                    resp.raise_for_status()
                    data = resp.json()
                contacts = [
                    {"name": p.get("name", "") or "",
                     "role": p.get("title", "") or "",
                     "email": p.get("email") or None,
                     "phone": None,
                     "social": p.get("linkedin_url", "") or None}
                    for p in (data.get("people") or [])
                    if p.get("name")
                ]
                return ProviderResult(ok=True, data={"contacts": contacts,
                                                      "provider": "apollo"})
            except httpx.HTTPStatusError as exc:
                code = exc.response.status_code
                if code in (401, 403, 429) and self.pool.rotate():
                    continue
                raise


class HunterContactAdapter:
    """FIND_CONTACT fallback via Hunter domain-search (1 credit/call)."""

    spec = ProviderSpec(provider_id="hunter", capability=Capability.FIND_CONTACT,
                        priority=20, cost_cents_per_call=1)

    def __init__(self):
        self.pool = KeyPool("HUNTER_API_KEY")

    def call(self, operation: str, params: dict[str, Any]) -> ProviderResult:
        domain = params.get("domain")
        if not domain or not len(self.pool):
            return ProviderResult(ok=False, error="HUNTER_API_KEY missing or no domain")
        while True:
            try:
                with httpx.Client(timeout=_TIMEOUT) as client:
                    resp = client.get(
                        "https://api.hunter.io/v2/domain-search",
                        params={"domain": domain, "limit": 3,
                                 "api_key": self.pool.current()})
                    resp.raise_for_status()
                    data = resp.json().get("data", {})
                contacts = [
                    {"name": " ".join(x for x in (e.get("first_name"), e.get("last_name")) if x) or None,
                     "role": e.get("position") or None,
                     "email": e.get("value"),
                     "phone": None,
                     "social": None}
                    for e in (data.get("emails") or [])
                    if e.get("value")
                ]
                return ProviderResult(ok=True, data={"contacts": contacts,
                                                      "provider": "hunter"})
            except httpx.HTTPStatusError as exc:
                code = exc.response.status_code
                if code in (401, 403, 429) and self.pool.rotate():
                    continue
                raise


class HunterVerifyAdapter:
    """VERIFY_EMAIL fallback: Hunter email-verifier after the SMTP probe —
    the waterfall's second hop for catch-all/ambiguous domains."""

    spec = ProviderSpec(provider_id="hunter-verify", capability=Capability.VERIFY_EMAIL,
                        priority=20, cost_cents_per_call=1)

    def __init__(self):
        self.pool = KeyPool("HUNTER_API_KEY")

    def call(self, operation: str, params: dict[str, Any]) -> ProviderResult:
        email = str(params.get("email", ""))
        if not email or "@" not in email or not len(self.pool):
            return ProviderResult(ok=False, error="HUNTER_API_KEY missing")
        while True:
            try:
                with httpx.Client(timeout=_TIMEOUT) as client:
                    resp = client.get(
                        "https://api.hunter.io/v2/email-verifier",
                        params={"email": email, "api_key": self.pool.current()})
                    resp.raise_for_status()
                    data = resp.json().get("data", {})
                result = data.get("result", "unknown")
                status = {"valid": "DELIVERABLE", "risky": "RISKY",
                          "invalid": "INVALID", "unknown": "UNKNOWN"}.get(result, "UNKNOWN")
                if data.get("status") == "catch_all":
                    status = "CATCH_ALL"
                return ProviderResult(ok=True, data={"status": status,
                                                      "provider_verified": status == "DELIVERABLE",
                                                      "details": {"hunter_result": result}})
            except httpx.HTTPStatusError as exc:
                code = exc.response.status_code
                if code in (401, 403, 429) and self.pool.rotate():
                    continue
                raise
