"""Provider capability contracts (ADR-0009). The domain asks for capabilities,
never vendors. Failure classification drives per-class behavior in the gateway."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol


class Capability(StrEnum):
    SEARCH_COMPANIES = "search_companies"
    ENRICH_COMPANY = "enrich_company"
    FIND_CONTACT = "find_contact"
    VERIFY_EMAIL = "verify_email"
    REASON = "reason"          # model gateway capability, mirrored here for costs


class FailureClass(StrEnum):
    TRANSIENT = "TRANSIENT"
    RATE_LIMIT = "RATE_LIMIT"
    CAPACITY = "CAPACITY"
    AUTH = "AUTH"
    VALIDATION = "VALIDATION"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    PERMANENT = "PERMANENT"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True)
class ProviderSpec:
    provider_id: str
    capability: Capability
    priority: int                    # lower wins the waterfall slot
    cost_cents_per_call: int = 0
    supports_idempotency: bool = False
    supports_batch: bool = False
    supports_cancel: bool = False
    daily_quota: int | None = None
    timeout_s: float = 30.0


@dataclass(frozen=True)
class ProviderCall:
    operation: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderResult:
    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    failure: FailureClass | None = None
    error: str = ""
    cost_cents: int = 0


class ProviderAdapter(Protocol):
    """The only surface a vendor integration may expose."""

    spec: ProviderSpec

    def call(self, operation: str, params: dict[str, Any]) -> ProviderResult: ...


def classify_exception(exc: Exception) -> FailureClass:
    """Map a raw exception to a FailureClass. Transport libs vary; we classify
    by the most common shapes so adapters stay thin."""
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    if "429" in text or "rate" in text:
        return FailureClass.RATE_LIMIT
    if "timeout" in name or "timed out" in text:
        return FailureClass.TRANSIENT
    if "connection" in name or "unreachable" in text or "temporarily" in text:
        return FailureClass.TRANSIENT
    if "401" in text or "403" in text or "auth" in text or "unauthorized" in text:
        return FailureClass.AUTH
    if "quota" in text or "capacity" in text or "503" in text:
        return FailureClass.CAPACITY
    if "400" in text or "validation" in text or "invalid" in text:
        return FailureClass.VALIDATION
    if "not supported" in text or "notimplemented" in name:
        return FailureClass.NOT_SUPPORTED
    return FailureClass.AMBIGUOUS
