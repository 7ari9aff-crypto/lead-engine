"""V6 FastAPI application factory.

Two mounting modes:
- create_app(container)      — standalone V6 API (apps.api entrypoint)
- build_v6_router(container) — mounted INTO the legacy app by api.bridge so
  the dashboard reaches V6 single-origin (same /api/v1 base path contract).

Routes are thin: validate → authenticate → authorize → use case → serialize.
No business logic lives here (ADR-0003).
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from v6api.dependencies import (
    Container,
    init_container,
    map_domain_errors,
    require_manager,
    require_principal,
    require_service,
)
from application.ports import Principal
from application.usecases.campaigns import CreateCampaign, JobQuery
from application.usecases.onboard import OnboardOrg
from application.usecases.pii_access import ContactPiiReader
from application.usecases.review import ReviewUseCase
from infrastructure.events.webhook_repo import WebhookEndpointRepo
from infrastructure.repos.system import BootstrapPg, JobRuntimePg, PlansReaderPg
from infrastructure.uow import PgUowFactory


class OnboardBody(BaseModel):
    slug: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=120)
    plan_code: str = "free"
    owner_ext_id: str = Field(min_length=3)


class CampaignBody(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    icp: dict[str, Any]
    budget_cents: int = 0


class DecisionBody(BaseModel):
    approve: bool
    reason: str = ""


class PiiBody(BaseModel):
    purpose: str
    request_id: str | None = None


class WebhookBody(BaseModel):
    url: str = Field(min_length=8)
    secret: str = Field(min_length=16)
    events: list[str] = ["*"]


def build_v6_router(container: Container) -> APIRouter:
    """All V6 business routes. Auth dependencies are app-level so the legacy
    mount can override them with the bridge (cookies/legacy claims)."""
    router = APIRouter()
    db = container.db
    uows = PgUowFactory(db, vault_engine=container.vault)
    jobs = JobRuntimePg(db)

    # Every list endpoint caps its page size: limit is client input, and an
    # uncapped query is a trivially cheap DoS against the pooled connection.
    @router.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok", "system": "lead-engine-v6"}

    @router.post("/api/v1/platform/onboard")
    def onboard(body: OnboardBody, request: Request,
                _service_ok: None = Depends(require_service)) -> dict:
        try:
            return OnboardOrg(BootstrapPg(db)).execute(
                body.slug, body.name, body.plan_code, body.owner_ext_id)
        except Exception as exc:
            raise map_domain_errors(exc) from exc

    @router.post("/api/v1/campaigns", status_code=201)
    def create_campaign(body: CampaignBody, request: Request,
                        principal: Principal = Depends(require_manager)) -> dict:
        try:
            return CreateCampaign(uows, PlansReaderPg(db), jobs).execute(
                principal.org_id or "", body.name, body.icp, body.budget_cents)
        except Exception as exc:
            raise map_domain_errors(exc) from exc

    @router.get("/api/v1/jobs")
    def list_jobs(request: Request, limit: int = Query(default=50, ge=1, le=200),
                  principal: Principal = Depends(require_principal)) -> list[dict]:
        return JobQuery(jobs).list(principal.org_id or "", limit)

    @router.get("/api/v1/jobs/{job_id}")
    def get_job(job_id: str, request: Request,
                principal: Principal = Depends(require_principal)) -> dict:
        try:
            return JobQuery(jobs).get(principal.org_id or "", job_id)
        except Exception as exc:
            raise map_domain_errors(exc) from exc

    @router.post("/api/v1/jobs/{job_id}/cancel")
    def cancel_job(job_id: str, request: Request,
                   principal: Principal = Depends(require_manager)) -> dict:
        try:
            ok = JobQuery(jobs).cancel(principal.org_id or "", job_id,
                                       principal.user_ext_id, "requested via api")
            return {"cancelled": ok}
        except Exception as exc:
            raise map_domain_errors(exc) from exc

    @router.get("/api/v1/review/pending")
    def pending_leads(request: Request,
                      limit: int = Query(default=50, ge=1, le=200),
                      principal: Principal = Depends(require_principal)) -> list[dict]:
        return ReviewUseCase(uows).pending(principal.org_id or "", limit)

    @router.post("/api/v1/review/leads/{lead_id}/decision")
    def decide_lead(lead_id: str, body: DecisionBody, request: Request,
                    principal: Principal = Depends(require_manager)) -> dict:
        try:
            return ReviewUseCase(uows).decide(
                principal.org_id or "", lead_id, principal.user_ext_id,
                body.approve, body.reason)
        except Exception as exc:
            raise map_domain_errors(exc) from exc

    @router.get("/api/v1/leads")
    def list_leads(request: Request, state: str | None = None,
                   limit: int = Query(default=50, ge=1, le=200),
                   principal: Principal = Depends(require_principal)) -> list[dict]:
        with uows(principal.org_id or "") as tx:
            return tx.repos.projects.list_leads(state=state, limit=limit)

    @router.get("/api/v1/leads/{lead_id}")
    def get_lead(lead_id: str, request: Request,
                 principal: Principal = Depends(require_principal)) -> dict:
        with uows(principal.org_id or "") as tx:
            lead = tx.repos.projects.get_lead(lead_id)
        if lead is None:
            raise HTTPException(status_code=404, detail="lead not found")
        return lead

    @router.get("/api/v1/lineage/leads/{lead_id}")
    def lead_lineage(lead_id: str, request: Request,
                     principal: Principal = Depends(require_principal)) -> dict:
        with uows(principal.org_id or "") as tx:
            lineage = tx.repos.lineage.lead_lineage(lead_id)
        if not lineage:
            raise HTTPException(status_code=404, detail="lead not found")
        return lineage

    @router.get("/api/v1/doctor/summary")
    def doctor_summary(request: Request,
                       principal: Principal = Depends(require_principal)) -> dict:
        report = container.doctor.run(container.settings, org=principal.org_id)
        return report.to_dict()

    @router.get("/api/v1/doctor")
    def doctor_full(request: Request,
                    principal: Principal = Depends(require_manager)) -> dict:
        report = container.doctor.run(container.settings, org=principal.org_id)
        return report.to_dict()

    @router.get("/api/v1/webhooks")
    def list_webhooks(request: Request,
                      principal: Principal = Depends(require_manager)) -> list[dict]:
        with uows(principal.org_id or "") as tx:
            return WebhookEndpointRepo(tx.cursor).list()

    @router.post("/api/v1/webhooks", status_code=201)
    def create_webhook(body: WebhookBody, request: Request,
                       principal: Principal = Depends(require_manager)) -> dict:
        try:
            with uows(principal.org_id or "") as tx:
                return WebhookEndpointRepo(tx.cursor).create(
                    body.url, body.secret, body.events)
        except Exception as exc:
            raise map_domain_errors(exc) from exc

    @router.post("/api/v1/webhooks/{endpoint_id}/disable")
    def disable_webhook(endpoint_id: str, request: Request,
                        principal: Principal = Depends(require_manager)) -> dict:
        with uows(principal.org_id or "") as tx:
            ok = WebhookEndpointRepo(tx.cursor).disable(endpoint_id)
        return {"disabled": ok}

    @router.post("/api/v1/leads/{lead_id}/pii")
    def read_lead_pii(lead_id: str, body: PiiBody, request: Request,
                      principal: Principal = Depends(require_manager)) -> dict:
        try:
            reader = ContactPiiReader(uows)
            return reader.read(principal.org_id or "", lead_id, body.purpose,
                               principal.user_ext_id, body.request_id)
        except Exception as exc:
            raise map_domain_errors(exc) from exc

    return router


def create_app(container: Container) -> FastAPI:
    """Standalone V6 app (apps.api entrypoint)."""

    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        yield
        container.db.close()

    init_container(container)
    app = FastAPI(title="Lead Engine V6", version="6.0.0", lifespan=_lifespan)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):  # noqa: ANN202
        if isinstance(exc, HTTPException):
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        http_exc = map_domain_errors(exc)
        return JSONResponse(status_code=http_exc.status_code,
                            content={"detail": http_exc.detail})

    app.include_router(build_v6_router(container))
    return app
