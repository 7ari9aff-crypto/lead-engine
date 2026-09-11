"""Platform activity feed: SQLite-backed event store + HTTP router.

Public surface:
  ActivityStore — append-only event log keyed by `kind` (e.g. job.started)
  get_router()  — FastAPI router to mount at /api/activity
"""
from .store import ActivityStore
from .api import get_router

__all__ = ["ActivityStore", "get_router"]
