"""Error taxonomy. Every layer raises these; the API maps them to responses."""
from __future__ import annotations


class V6Error(Exception):
    """Base class for all V6 errors."""


class DomainError(V6Error):
    """A business rule was violated."""


class NotFoundError(V6Error):
    """The requested aggregate does not exist (or belongs to another tenant)."""


class AuthorizationError(V6Error):
    """The principal lacks the required role/scope."""


class PolicyBlocked(V6Error):
    """Governance gate returned BLOCKED."""


class PolicyNeedsReview(V6Error):
    """Governance gate requires human review."""


class EntitlementExceeded(V6Error):
    """The plan does not allow this operation."""


class LeaseLostError(V6Error):
    """A fenced write matched 0 rows: the lease was taken by a newer attempt."""


class IdempotencyConflict(V6Error):
    """The same idempotency key was reused with a different request."""
