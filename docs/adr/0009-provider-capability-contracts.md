# ADR-0009 — Providers behind capability contracts

Status: accepted (implements locked invariants)

The domain never knows Apollo, Hunter, Tavily, Gemini by name. It requests
capabilities:

```
SearchCompanies | EnrichCompany | FindContact | VerifyEmail | Reason
```

The Provider Gateway owns the registry (capability, priority, cost, quota,
health, supports_idempotency…), the waterfall (cheap → mid → specialist →
fallback), the budget check before every call, failure classification
(TRANSIENT, RATE_LIMIT, CAPACITY, AUTH, VALIDATION, NOT_SUPPORTED, PERMANENT,
AMBIGUOUS) and per-class behavior. Every external call is recorded in
`effects.effect_ledger` with a deterministic idempotency key
hash(tenant, job, step, provider, normalized_operation); providers that
support idempotency get effectively-once behavior, others get
ledger + reconciliation — never blind retries.
