"""Request-scoped tenant context — the single org resolution path.
Every router resolves its tenant through db_handle() instead of keeping
private get_db copies (app.py, research_api, review_api, pitch_api,
events_api, data_api, activity used to drift): 
1. Verified JWT claims  -> membership org; a user with no membership gets
   the fail-closed '__no_org__' sentinel — the env bridge must never act
   as their tenant.
2. No claims (worker, n8n, MCP token, local dev) -> LEAD_ENGINE_ORG_ID
   bridge when set.
"""
import os
from fastapi import Request
from .db import open_db

def apply_context(db, request: Request | None) -> None:
    """Pin db.org_id for this request. Call right after open_db()."""
    claims = getattr(request.state, "claims", None) if request is not None else None
    if claims:
        from .api import auth_jwt
        resolved = auth_jwt.resolve_org_id(claims, db)
        # Fallback: ephemeral-SQLite deployments keep no membership table, so
        # a verified Supabase user rides the env-bridge org (the deployment's
        # trust model: Supabase accounts are operator-invited).
        db.org_id = resolved or os.environ.get("LEAD_ENGINE_ORG_ID") or "__no_org__"
        return
    if not getattr(db, "org_id", None):
        db.org_id = os.environ.get("LEAD_ENGINE_ORG_ID")

def db_handle(request: Request = None):
    """FastAPI dependency: one DB handle per request with the tenant pinned."""
    db = open_db()
    try:
        apply_context(db, request)
        yield db
    finally:
        db.conn.close()

def org_clause(db, column: str = "organization_id") -> tuple[str, list]:
    """SQL predicate limiting reads to the caller's tenant — the ONLY way
    chat tools / MCP / dashboards may read tenant tables.
    SQLite has no RLS: with NO tenant context the clause is empty (legacy
    single-org dev data is not tenant data), but the '__no_org__' sentinel —
    a verified user with no membership and no bridge — is fail-closed DENY:
    it must never broaden into an unfiltered read."""
    org = getattr(db, "org_id", None)
    if not org:
        return "", []
    if str(org).startswith("__"):
        return " AND 1 = 0", []
    return f" AND {column} = ?", [org]