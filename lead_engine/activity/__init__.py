"""Platform activity feed: SQLite-backed event store + HTTP router.

Public surface:
  ActivityStore   — append-only event log keyed by `kind` (e.g. job.started)
  AuditTrailStore — tenant-scoped single-statement reads over audit_logs
  get_router()    — FastAPI router to mount at /api/activity and /api/audit
"""
from .store import ActivityStore, AuditTrailStore
from .api import get_router

__all__ = ["ActivityStore", "AuditTrailStore", "get_router"]
