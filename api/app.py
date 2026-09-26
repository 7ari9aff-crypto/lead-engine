"""V6 FastAPI application factory.

Routes are thin: validate → authenticate → authorize → use case → serialize.
No business logic lives here (ADR-0003). All business routes live under
/api/v1 with tenant scoping from the verified principal.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.dependencies import (
    Container,
    get_container,
    init_container,
    map_domain_errors,
    require_manager,
    require_principal,
    require_service,
)
from application.usecases.campaigns import CreateCampaign, JobQuery
from application.usecases.onboard import OnboardOrg
from application.usecases.pii_access import ContactPiiReader
from application.usecases.review import ReviewUseCase
from infrastructure.repos.system import BootstrapPg, JobRuntimePg, PlansReaderPg
from infrastructure.uow import PgUowFactory


@asynccontextmanager
async def _lifespan(app: FastAPI):
    yield
    container = get_container()
    container.db.close()



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


def create_app(container: Container) -> FastAPI:
    init_container(container)
    app = FastAPI(title="Lead Engine V6", version="6.0.0", lifespan=_lifespan)
    db = container.db
    vault = container.vault
    uows = PgUowFactory(db, vault_engine=vault)
    jobs = JobRuntimePg(db)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):  # noqa: ANN202
        if isinstance(exc, HTTPException):
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        http_exc = map_domain_errors(exc)
        return JSONResponse(status_code=http_exc.status_code,
                            content={"detail": http_exc.detail})

    # ---------------- health ----------------
    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok", "system": "lead-engine-v6"}

    # ---------------- platform ----------------
    @app.post("/api/v1/platform/onboard")
    def onboard(body: OnboardBody, request: Request) -> dict:
        require_service(request)
        try:
            return OnboardOrg(BootstrapPg(db)).execute(
                body.slug, body.name, body.plan_code, body.owner_ext_id)
        except Exception as exc:
            raise map_domain_errors(exc) from exc

    # ---------------- campaigns & jobs ----------------
    @app.post("/api/v1/campaigns", status_code=201)
    def create_campaign(body: CampaignBody, request: Request) -> dict:
        principal = require_manager(request)
        try:
            return CreateCampaign(uows, PlansReaderPg(db), jobs).execute(
                principal.org_id or "", body.name, body.icp, body.budget_cents)
        except Exception as exc:
            raise map_domain_errors(exc) from exc

    @app.get("/api/v1/jobs")
    def list_jobs(request: Request, limit: int = 50) -> list[dict]:
        principal = require_principal(request)
        return JobQuery(jobs).list(principal.org_id or "", limit)

    @app.get("/api/v1/jobs/{job_id}")
    def get_job(job_id: str, request: Request) -> dict:
        principal = require_principal(request)
        try:
            return JobQuery(jobs).get(principal.org_id or "", job_id)
        except Exception as exc:
            raise map_domain_errors(exc) from exc

    @app.post("/api/v1/jobs/{job_id}/cancel")
    def cancel_job(job_id: str, request: Request) -> dict:
        principal = require_manager(request)
        try:
            ok = JobQuery(jobs).cancel(principal.org_id or "", job_id,
                                       principal.user_ext_id, "requested via api")
            return {"cancelled": ok}
        except Exception as exc:
            raise map_domain_errors(exc) from exc

    # ---------------- review boundary ----------------
    @app.get("/api/v1/review/pending")
    def pending_leads(request: Request, limit: int = 50) -> list[dict]:
        principal = require_principal(request)
        return ReviewUseCase(uows).pending(principal.org_id or "", limit)

    @app.post("/api/v1/review/leads/{lead_id}/decision")
    def decide_lead(lead_id: str, body: DecisionBody, request: Request) -> dict:
        principal = require_manager(request)
        try:
            return ReviewUseCase(uows).decide(
                principal.org_id or "", lead_id, principal.user_ext_id,
                body.approve, body.reason)
        except Exception as exc:
            raise map_domain_errors(exc) from exc

    # ---------------- leads projection ----------------
    @app.get("/api/v1/leads")
    def list_leads(request: Request, state: str | None = None, limit: int = 50) -> list[dict]:
        principal = require_principal(request)
        with uows(principal.org_id or "") as tx:
            return tx.repos.projects.list_leads(state=state, limit=limit)

    @app.get("/api/v1/leads/{lead_id}")
    def get_lead(lead_id: str, request: Request) -> dict:
        principal = require_principal(request)
        with uows(principal.org_id or "") as tx:
            lead = tx.repos.projects.get_lead(lead_id)
        if lead is None:
            raise HTTPException(status_code=404, detail="lead not found")
        return lead

    # ---------------- business lineage ----------------
    @app.get("/api/v1/lineage/leads/{lead_id}")
    def lead_lineage(lead_id: str, request: Request) -> dict:
        principal = require_principal(request)
        with uows(principal.org_id or "") as tx:
            lineage = tx.repos.lineage.lead_lineage(lead_id)
        if not lineage:
            raise HTTPException(status_code=404, detail="lead not found")
        return lineage

    # ---------------- PII access (purpose-bound) ----------------
    @app.post("/api/v1/leads/{lead_id}/pii")
    def read_lead_pii(lead_id: str, body: PiiBody, request: Request) -> dict:
        principal = require_manager(request)
        try:
            reader = ContactPiiReader(uows, vault)
            return reader.read(principal.org_id or "", lead_id, body.purpose,
                               principal.user_ext_id, body.request_id)
        except Exception as exc:
            raise map_domain_errors(exc) from exc

    return app
