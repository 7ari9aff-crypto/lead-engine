"""Tenant provisioning state machine (Phase 3, as code).

REQUESTED -> PROVISIONING -> ACTIVE, with FAILED on any step error.
Steps append to a JSONB trail so a half-created tenant is always visible
and resumable/rollbackable. Dedicated-infrastructure provisioning (K8s
namespaces, dedicated DBs) plugs in at the PROVISIONING step — pooled
tenants complete immediately because the shared plane is always ready.
"""
import json

from .db import utcnow

REQUESTED = "REQUESTED"
PROVISIONING = "PROVISIONING"
ACTIVE = "ACTIVE"
FAILED = "FAILED"

TRANSITIONS = {
    REQUESTED: {PROVISIONING, FAILED},
    PROVISIONING: {ACTIVE, FAILED},
    ACTIVE: set(),
    FAILED: {PROVISIONING},  # retry path
}


class IllegalTransition(Exception):
    pass


def _cast(db) -> str:
    """Parameter cast suffix: ?::jsonb on Postgres, plain ? on SQLite."""
    return "::jsonb" if getattr(db, "dialect", "sqlite") == "postgres" else ""


def _json_array_literal(db) -> str:
    return "'[]'::jsonb" if _cast(db) else "'[]'"


def start(db, org_id: str, requested_by: str | None = None,
          isolation_level: str = "pooled") -> str:
    db.execute(
        "INSERT INTO tenant_provisioning (org_id, state, isolation_level, steps,"
        " requested_by, created_at, updated_at)"
        f" VALUES (?, ?, ?, {_json_array_literal(db)}, ?, ?, ?)"
        " ON CONFLICT (org_id) DO NOTHING",
        (org_id, REQUESTED, isolation_level, requested_by, utcnow(), utcnow()))
    return REQUESTED


def _transition(db, org_id: str, to_state: str) -> None:
    row = db.one("SELECT state FROM tenant_provisioning WHERE org_id = ?", (org_id,))
    if not row:
        raise IllegalTransition(f"no provisioning record for {org_id}")
    if to_state not in TRANSITIONS.get(row["state"], set()):
        raise IllegalTransition(f"{row['state']} -> {to_state} is not allowed")
    db.execute(
        "UPDATE tenant_provisioning SET state = ?, updated_at = ? WHERE org_id = ?",
        (to_state, utcnow(), org_id))


def _save_steps(db, org_id: str, steps: list) -> None:
    db.execute(
        "UPDATE tenant_provisioning SET steps = ?" + _cast(db) +
        ", updated_at = ? WHERE org_id = ?",
        (json.dumps(steps, ensure_ascii=False), utcnow(), org_id))


def provision(db, org_id: str, isolation_level: str = "pooled",
              step_handlers: dict | None = None) -> dict:
    """Run the full state machine for one tenant. step_handlers lets the
    dedicated-infrastructure path inject real provisioning work (K8s
    namespace, dedicated DB) without changing this module."""
    current = status(db, org_id)
    if current and current["state"] == ACTIVE:
        # idempotent: an ACTIVE tenant needs no reprovisioning
        return {"org_id": org_id, "state": ACTIVE,
                "steps": json.loads(current["steps"] or "[]")}
    start(db, org_id, isolation_level=isolation_level)
    _transition(db, org_id, PROVISIONING)
    steps = []

    def _step(name: str, fn=None) -> bool:
        try:
            detail = fn() if fn else "ok"
            steps.append({"step": name, "status": "ok", "detail": detail})
            _save_steps(db, org_id, steps)
            return True
        except Exception as exc:
            steps.append({"step": name, "status": "failed",
                          "detail": f"{type(exc).__name__}: {exc}"})
            db.execute(
                "UPDATE tenant_provisioning SET steps = ?" + _cast(db) +
                ", error = ?, state = ?, updated_at = ? WHERE org_id = ?",
                (json.dumps(steps, ensure_ascii=False), str(exc), FAILED,
                 utcnow(), org_id))
            return False

    org_table = ("public.organizations"
                 if getattr(db, "dialect", "sqlite") == "postgres"
                 else "organizations")
    if not _step("validate_organization",
                 lambda: db.one(f"SELECT slug FROM {org_table}"
                                " WHERE id = ?", (org_id,))["slug"]):
        return {"org_id": org_id, "state": FAILED, "steps": steps}

    if isolation_level == "pooled":
        ok = _step("shared_plane_ready")  # shared plane is always ready
    else:
        handler = (step_handlers or {}).get(isolation_level)
        ok = _step(f"provision_{isolation_level}", handler)
    if not ok:
        return {"org_id": org_id, "state": FAILED, "steps": steps}

    _transition(db, org_id, ACTIVE)
    steps.append({"step": "activate", "status": "ok"})
    _save_steps(db, org_id, steps)
    return {"org_id": org_id, "state": ACTIVE, "steps": steps}


def status(db, org_id: str) -> dict | None:
    return db.one("SELECT * FROM tenant_provisioning WHERE org_id = ?", (org_id,))
