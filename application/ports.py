"""Ports (protocols) the application layer depends on. Infrastructure and
runtime implement them. Keeping these as Protocols is what makes the boundary
testable: domain/application never import psycopg, httpx or vendors."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from contracts.events import EventEnvelope


@dataclass(frozen=True)
class Principal:
    """Authenticated caller resolved by the API middleware."""
    org_id: str | None
    user_ext_id: str
    role: str                      # owner | admin | member | service
    is_service: bool = False

    def can_manage(self) -> bool:
        return self.is_service or self.role in ("owner", "admin")


# --------------------------------------------------------------------------
# Clock
# --------------------------------------------------------------------------
@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime: ...


# --------------------------------------------------------------------------
# Repositories (tenant-scoped; every method belongs to the open transaction)
# --------------------------------------------------------------------------
@runtime_checkable
class PlatformRepo(Protocol):
    def get_plan_limits(self, plan_code: str) -> dict[str, Any]: ...
    def record_usage(self, kind: str, units: float = 0, cost_cents: float = 0,
                     ref: dict[str, Any] | None = None) -> None: ...
    def create_org(self, org_id: str, slug: str, name: str, plan_code: str) -> str: ...
    def add_member(self, org_id: str, user_ext_id: str, role: str) -> None: ...
    def find_membership(self, user_ext_id: str) -> dict[str, Any] | None: ...
    def get_org(self, org_id: str) -> dict[str, Any] | None: ...


@runtime_checkable
class AcquisitionRepo(Protocol):
    def create_campaign(self, name: str, icp_version_id: str,
                        budget_cents: int = 0) -> str: ...
    def get_campaign(self, campaign_id: str) -> dict[str, Any] | None: ...
    def set_campaign_state(self, campaign_id: str, state: str) -> None: ...
    def create_icp_version(self, profile_name: str, definition: dict[str, Any]) -> str: ...
    def get_icp_definition(self, version_id: str) -> dict[str, Any] | None: ...


@runtime_checkable
class CompanyRepo(Protocol):
    def find_by_domain(self, domain: str) -> dict[str, Any] | None: ...
    def find_by_normalized_name(self, name: str) -> dict[str, Any] | None: ...
    def create_company(self, company_id: str, canonical_name: str, domain: str | None,
                       country: str | None, industry: str | None, city: str | None) -> str: ...
    def add_identifier(self, company_id: str, kind: str, value: str,
                       source_id: str | None = None) -> None: ...


@runtime_checkable
class ClaimsRepo(Protocol):
    def get_or_create_source(self, kind: str, url: str | None, provider_id: str | None,
                             content_hash: str | None) -> str: ...
    def add_observation(self, company_id: str, field_name: str, value: str | None,
                        source_id: str | None, extraction_method: str,
                        confidence: float) -> None: ...
    def upsert_claim(self, company_id: str, field_name: str, value: str | None,
                     source_id: str | None, extraction_method: str, confidence: float) -> None: ...
    def claims_summary(self, company_id: str) -> dict[str, Any]: ...


@runtime_checkable
class ContactsRepo(Protocol):
    def find_or_create_contact(self, company_id: str, name: str | None, role: str | None,
                               source_id: str | None) -> str: ...
    def attach_email_ref(self, contact_id: str, pii_ref_id: str,
                         masked: str | None = None) -> None: ...
    def attach_phone_ref(self, contact_id: str, pii_ref_id: str,
                         masked: str | None = None) -> None: ...
    def attach_social(self, contact_id: str, value: str) -> None: ...
    def list_company_contacts(self, company_id: str) -> list[dict[str, Any]]: ...


@runtime_checkable
class IntelligenceRepo(Protocol):
    def add_raw_result(self, job_id: str, provider_id: str, query: str, url: str,
                       title: str | None, snippet: str | None) -> bool: ...
    def mark_visited(self, job_id: str, url: str) -> bool: ...
    def record_enrichment(self, company_id: str, provider_id: str, operation: str,
                          status: str, failure_class: str | None = None,
                          cost_cents: float = 0, effect_id: str | None = None) -> None: ...
    def cache_verification(self, cache_key: str, status: str, evidence: dict[str, Any],
                           expires_at: datetime) -> None: ...
    def get_cached_verification(self, cache_key: str) -> dict[str, Any] | None: ...
    def record_verification(self, contact_id: str, kind: str, pii_ref_id: str | None,
                            status: str, provider_id: str, evidence: dict[str, Any]) -> None: ...
    def company_verification_statuses(self, company_id: str) -> dict[str, str]: ...
    def add_scoring_record(self, company_id: str, score: float, score_version: str,
                           input_snapshot: dict[str, Any], explanations: list[str]) -> None: ...
    def add_qualification_record(self, company_id: str, campaign_id: str | None,
                                 decision: str, reasons: list[str],
                                 icp_version_id: str | None,
                                 policy_version: str) -> None: ...
    def add_intent_signal(self, company_id: str, kind: str, signal: str,
                          source_id: str | None = None) -> None: ...
    def company_context(self, company_id: str) -> dict[str, Any]: ...


@runtime_checkable
class GovernanceRepo(Protocol):
    def get_policy_rules(self) -> dict[str, Any]: ...
    def record_decision(self, subject_type: str, subject_id: str, operation: str,
                        decision: str, policy_version: str, legal_basis: str,
                        decision_reason: str, decided_by: str) -> str: ...
    def is_suppressed(self, kind: str, value: str) -> bool: ...
    def add_suppression(self, kind: str, value: str, reason: str) -> None: ...


@runtime_checkable
class ProjectsRepo(Protocol):
    def upsert_lead(self, campaign_id: str | None, company_id: str, contact_id: str | None,
                    icp_version_id: str | None, display: dict[str, Any],
                    masked_email: str | None, masked_phone: str | None,
                    email_status: str | None, score: float | None,
                    score_version: str | None, decision: str) -> str: ...
    def list_leads(self, state: str | None = None, limit: int = 50) -> list[dict[str, Any]]: ...
    def get_lead(self, lead_id: str) -> dict[str, Any] | None: ...
    def decide_lead(self, lead_id: str, state: str, decided_by: str) -> bool: ...


@runtime_checkable
class LineageRepo(Protocol):
    def lead_lineage(self, lead_id: str) -> dict[str, Any]: ...


@runtime_checkable
class PiiVaultPort(Protocol):
    """Store/retrieve PII. Plaintext exists only inside the vault boundary."""
    def store(self, kind: str, value: str) -> str: ...
    def decrypt(self, ref_id: str, purpose: str, actor: str,
                request_id: str | None = None) -> str: ...
    def masked(self, kind: str, value: str) -> str: ...


@runtime_checkable
class Repositories(Protocol):
    platform: PlatformRepo
    acquisition: AcquisitionRepo
    companies: CompanyRepo
    claims: ClaimsRepo
    contacts: ContactsRepo
    intelligence: IntelligenceRepo
    governance: GovernanceRepo
    projects: ProjectsRepo
    lineage: LineageRepo


@dataclass
class JobContext:
    """Everything a job handler may touch for the current attempt."""
    job_id: str
    org_id: str
    campaign_id: str | None
    job_type: str
    payload: dict[str, Any]
    checkpoint: dict[str, Any] = field(default_factory=dict)
    lease_token: str = ""
    lease_version: int = 0
    worker_id: str = ""


# --------------------------------------------------------------------------
# Unit of work: one tenant-scoped transaction; repos + event emission share it
# --------------------------------------------------------------------------
@runtime_checkable
class UnitOfWork(Protocol):
    def __enter__(self) -> Any: ...
    def __exit__(self, *exc: Any) -> None: ...
    @property
    def repos(self) -> Repositories: ...
    @property
    def vault(self) -> PiiVaultPort: ...
    def emit(self, event: EventEnvelope) -> None: ...


@runtime_checkable
class UowFactory(Protocol):
    """Opens one tenant-scoped unit of work (optionally job-correlated)."""
    def __call__(self, org_id: str, job: Any | None = None) -> UnitOfWork: ...


@runtime_checkable
class BootstrapPort(Protocol):
    """System-level platform operations (org creation, membership)."""
    def create_org(self, org_id: str, slug: str, name: str, plan_code: str,
                   owner_ext_id: str) -> str: ...
    def plan_exists(self, plan_code: str) -> bool: ...


@runtime_checkable
class PlansReader(Protocol):
    def plan_for_org(self, org_id: str) -> dict[str, Any]: ...


@runtime_checkable
class JobRuntime(Protocol):
    """The durable runtime surface the application may use (implemented by
    the runtime plane). All state lives in PostgreSQL (ADR-0004)."""
    def enqueue(self, org_id: str, job_type: str, payload: dict[str, Any],
                queue: str = "default", campaign_id: str | None = None) -> str: ...
    def active_count(self, org_id: str) -> int: ...
    def get(self, org_id: str, job_id: str) -> dict[str, Any] | None: ...
    def list(self, org_id: str, limit: int = 50) -> list[dict[str, Any]]: ...
    def events(self, job_id: str, limit: int = 50) -> list[dict[str, Any]]: ...
    def cancel(self, org_id: str, job_id: str, cancelled_by: str, reason: str) -> bool: ...
    def resume(self, org_id: str, job_id: str) -> bool: ...


@runtime_checkable
class JobOps(Protocol):
    """Fenced runtime surface handed to a handler for the current attempt
    (implemented by runtime.worker.JobOps). Handlers drive progress ONLY
    through these fenced calls — never by writing runtime tables directly."""
    ctx: JobContext
    gateway: Any
    model_gateway: Any

    def checkpoint(self, data: dict[str, Any], state: str | None = None) -> None: ...
    def set_phase(self, state: str) -> None: ...
    def heartbeat(self) -> bool: ...
    def cancel_requested(self) -> bool: ...
    def apply_cancellation(self) -> bool: ...
    def finish_cancelled(self) -> None: ...
    def uow(self) -> UnitOfWork: ...
