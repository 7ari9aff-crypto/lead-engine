"""Deterministic fake providers for tests and offline development.

They simulate the real world precisely enough to exercise waterfall, ledger,
classification and cache behavior — including failure injection.
"""
from __future__ import annotations

from typing import Any

from contracts.providers import Capability, ProviderResult, ProviderSpec


class FakeSearchProvider:
    def __init__(self, provider_id: str, priority: int, results: list[dict[str, Any]] | None = None,
                 fail_with: Exception | None = None, cost: int = 0):
        self.spec = ProviderSpec(provider_id=provider_id, capability=Capability.SEARCH_COMPANIES,
                                 priority=priority, cost_cents_per_call=cost)
        self._results = results or []
        self._fail = fail_with
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call(self, operation: str, params: dict[str, Any]) -> ProviderResult:
        self.calls.append((operation, params))
        if self._fail is not None:
            raise self._fail
        query = str(params.get("query", "")).lower()
        matched = [r for r in self._results
                   if all(word in query for word in str(r.get("match", "")).lower().split())
                   or r.get("always", False)]
        return ProviderResult(ok=True, data={"results": matched},
                              cost_cents=self.spec.cost_cents_per_call)


class FakeVerifyProvider:
    def __init__(self, provider_id: str, priority: int, mapping: dict[str, str] | None = None,
                 default: str = "UNKNOWN", fail_with: Exception | None = None):
        self.spec = ProviderSpec(provider_id=provider_id, capability=Capability.VERIFY_EMAIL,
                                 priority=priority, supports_idempotency=True)
        self._mapping = mapping or {}
        self._default = default
        self._fail = fail_with
        self.calls: list[str] = []

    def call(self, operation: str, params: dict[str, Any]) -> ProviderResult:
        email = str(params.get("email", ""))
        self.calls.append(email)
        if self._fail is not None:
            raise self._fail
        status = self._mapping.get(email, self._default)
        return ProviderResult(ok=True, data={"status": status,
                                             "provider_verified": status != "UNKNOWN"})


class FakeContactProvider:
    """Deterministic contact enrichment keyed by company domain."""

    def __init__(self, provider_id: str = "fake-contact", priority: int = 10,
                 contacts_by_domain: dict[str, list[dict[str, Any]]] | None = None,
                 cost: int = 2):
        self.spec = ProviderSpec(provider_id=provider_id, capability=Capability.FIND_CONTACT,
                                 priority=priority, cost_cents_per_call=cost)
        self._by_domain = contacts_by_domain or {}
        self.calls: list[str] = []

    def call(self, operation: str, params: dict[str, Any]) -> ProviderResult:
        domain = str(params.get("domain") or "")
        self.calls.append(domain)
        contacts = self._by_domain.get(domain, [])
        return ProviderResult(ok=True, data={"contacts": contacts},
                              cost_cents=self.spec.cost_cents_per_call)


class FlakyProvider(FakeSearchProvider):
    """Fails the first N calls with the given exception, then succeeds —
    exercises waterfall fallback and classification."""

    def __init__(self, provider_id: str, priority: int, results: list[dict[str, Any]],
                 fail_times: int, exc: Exception):
        super().__init__(provider_id, priority, results)
        self._fail_times = fail_times
        self._exc = exc

    def call(self, operation: str, params: dict[str, Any]) -> ProviderResult:
        if self._fail_times > 0:
            self._fail_times -= 1
            raise self._exc
        return super().call(operation, params)
