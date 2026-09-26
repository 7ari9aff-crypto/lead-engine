# ADR-0003 — Modular monolith, strict import boundaries

Status: accepted

One deployable codebase, strict module boundaries:

```
api → application → domain → contracts
                 ↘ ports → infrastructure, runtime
```

- `domain/` imports nothing from api/application/infrastructure/runtime.
  No FastAPI, no Redis, no provider SDKs, no environment access.
- `application/` defines ports (protocols) and use cases; infrastructure and
  runtime implement the ports.
- `runtime/` applies execution (leases, checkpoints) around application handlers.
- `api/` routes are thin: validate → authenticate → authorize → use case → serialize.
- The layered rule is enforced by `tests/v6/test_import_boundaries.py` so it
  cannot rot.
