"""Provider Gateway (ADR-0009).

Owns: registry, waterfall (capability → policy/budget → provider order),
failure classification behavior, usage accounting, and the effect ledger that
makes external calls idempotent-or-reconciled (never blindly retried).

The domain never sees vendor names — only Capability + data.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from contracts.providers import Capability, FailureClass, ProviderResult, ProviderSpec


def idempotency_key(tenant_id: str, job_id: str | None, step_id: str | None,
                    provider_id: str, operation: str, params: dict[str, Any]) -> str:
    canonical = json.dumps(params or {}, sort_keys=True, separators=(",", ":"), default=str)
    request_hash = hashlib.sha256(canonical.encode()).hexdigest()
    basis = f"{tenant_id}|{job_id or '-'}|{step_id or '-'}|{provider_id}|{operation}"
    key = hashlib.sha256(basis.encode()).hexdigest()[:32] + request_hash[:16]
    return key, request_hash


class _Ledger:
    """Effect ledger backed by the caller's connection (same tx as business
    mutation). reserve() returns (effect_id, already_effected)."""

    def __init__(self, cur):
        self.cur = cur

    def reserve(self, org_id: str, job_id: str | None, step_id: str | None,
                spec: ProviderSpec, operation: str,
                params: dict[str, Any]) -> tuple[str, bool]:
        key, request_hash = idempotency_key(org_id, job_id, step_id,
                                            spec.provider_id, operation, params)
        existing = self.cur.execute(
            """SELECT id, status FROM effects.effect_ledger WHERE idempotency_key = %s""",
            (key,),
        ).fetchone()
        if existing:
            if existing["status"] == "failed":
                self.cur.execute(
                    "UPDATE effects.effect_ledger SET status = 'reserved' WHERE id = %s",
                    (existing["id"],),
                )
                return str(existing["id"]), False
            return str(existing["id"]), existing["status"] == "succeeded"
        row = self.cur.execute(
            """INSERT INTO effects.effect_ledger
                 (org_id, job_id, step_id, provider_id, operation, idempotency_key,
                  request_hash, status)
               VALUES (%s, %s, %s, %s, %s, %s, %s, 'reserved')
               RETURNING id""",
            (org_id, job_id, step_id, spec.provider_id, operation, key, request_hash),
        ).fetchone()
        return str(row["id"]), False

    def complete(self, effect_id: str, ok: bool, cost_cents: int,
                 result_digest: str | None, failure_class: str | None = None) -> None:
        # Ledger status is constrained to reserved/succeeded/failed/uncertain;
        # the failure CLASS lives in enrichment_attempts / job error, not here.
        if ok:
            final = "succeeded"
        elif failure_class == "AMBIGUOUS":
            final = "uncertain"
        else:
            final = "failed"
        self.cur.execute(
            """UPDATE effects.effect_ledger
               SET status = %s, cost_cents = %s, result_digest = %s
               WHERE id = %s""",
            (final, cost_cents, result_digest, effect_id),
        )


class ProviderGateway:
    """Executes one capability through the registered waterfall."""

    def __init__(self, clock=None):
        self._registry: dict[Capability, list] = {}
        self._clock = clock

    def register(self, adapter) -> None:
        self._registry.setdefault(adapter.spec.capability, []).append(adapter)
        self._registry[adapter.spec.capability].sort(key=lambda a: a.spec.priority)

    def adapters(self, capability: Capability) -> list:
        return list(self._registry.get(capability, []))

    def execute(self, cur, org_id: str, capability: Capability, operation: str,
                params: dict[str, Any], job_id: str | None = None,
                step_id: str | None = None,
                budget_cents: int | None = None) -> ProviderResult:
        """Run the waterfall. Reserve the effect BEFORE calling; complete it
        after. An already-succeeded identical effect is NOT re-executed."""
        ledger = _Ledger(cur)
        for adapter in self.adapters(capability):
            effect_id, already = ledger.reserve(org_id, job_id, step_id,
                                                adapter.spec, operation, params)
            if already:
                return ProviderResult(ok=True, data={"cached_effect": effect_id})

            if budget_cents is not None and adapter.spec.cost_cents_per_call > budget_cents:
                return ProviderResult(ok=False, failure=FailureClass.CAPACITY,
                                      error="budget exhausted before provider call")

            try:
                result = adapter.call(operation, params)
            except Exception as exc:  # noqa: BLE001 — classification IS the contract
                from contracts.providers import classify_exception

                result = ProviderResult(ok=False, failure=classify_exception(exc),
                                        error=f"{type(exc).__name__}: {exc}")

            if result.ok:
                ledger.complete(effect_id, True, result.cost_cents, None)
                return result

            ledger.complete(effect_id, False, 0, None,
                            failure_class=result.failure.value if result.failure else None)
            if result.failure in (FailureClass.TRANSIENT, FailureClass.RATE_LIMIT,
                                  FailureClass.CAPACITY, FailureClass.AMBIGUOUS):
                continue  # try the next provider in the waterfall
            return result  # AUTH/VALIDATION/NOT_SUPPORTED/PERMANENT are terminal

        return ProviderResult(ok=False, failure=FailureClass.CAPACITY,
                              error="no provider available for capability")
