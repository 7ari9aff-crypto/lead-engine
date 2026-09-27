"""The acquisition pipeline handler.

One durable job walks the lifecycle PLANNING → DISCOVERING → ENRICHING →
VERIFYING → SCORING → QUALIFYING → READY_FOR_REVIEW, checkpointing at every
phase boundary and after every bounded unit (per query / per company) so a
crashed worker resumes exactly where it stopped (ADR-0004).

Invariants enforced here:
- governance evaluate + record BEFORE regulated operations (§10);
- identity resolution gates company creation (§4.3/§4.6);
- contacts store PII refs + masked values only (ADR-0006);
- lead rows are projections built from claims/verification/score/decision (§6);
- lead creation emits LEAD_READY_FOR_REVIEW in the SAME transaction (ADR-0005).
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from application.ports import JobContext, JobOps
from contracts.errors import DomainError
from contracts.events import (
    LEAD_READY_FOR_REVIEW,
    POLICY_DECISION_RECORDED,
    VERIFICATION_COMPLETED,
    EventEnvelope,
)
from contracts.providers import Capability
from domain.acquisition.company import (
    domain_from_url,
    extract_contacts,
    normalize_name,
    resolve_identity,
)
from domain.acquisition.icp import build_query_plan, is_empty_plan
from domain.governance.policy import VERSION as POLICY_VERSION
from domain.governance.policy import GovernanceDecision, PolicyInput, default_rules, evaluate
from domain.intelligence.scoring import (
    QualificationInputs,
    ScoreInputs,
    compute_score,
    decide,
)
from domain.intelligence.verification import VerificationStatus, promote
from domain.shared.types import QualificationDecision

log = logging.getLogger("v6.pipeline")

STATUS_ORDER = [VerificationStatus.DELIVERABLE, VerificationStatus.RISKY,
                VerificationStatus.CATCH_ALL, VerificationStatus.UNKNOWN,
                VerificationStatus.INVALID]


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _best_status(current: VerificationStatus | None,
                 candidate: VerificationStatus) -> VerificationStatus:
    if current is None:
        return candidate
    return min(current, candidate, key=STATUS_ORDER.index)


class AcquisitionPipelineHandler:
    def __call__(self, ctx: JobContext, ops: JobOps) -> str:
        checkpoint = dict(ctx.checkpoint or {})
        phase = checkpoint.get("phase", "PLANNING")
        if phase == "PLANNING":
            checkpoint = self._plan(ctx, ops)
            phase = checkpoint["phase"]
        if phase == "DISCOVERING":
            checkpoint = self._discover(ctx, ops, checkpoint)
            phase = checkpoint["phase"]
        if phase == "ENRICHING":
            checkpoint = self._enrich(ctx, ops, checkpoint)
            phase = checkpoint["phase"]
        if phase == "VERIFYING":
            checkpoint = self._verify(ctx, ops, checkpoint)
            phase = checkpoint["phase"]
        if phase == "SCORING":
            checkpoint = self._score(ctx, ops, checkpoint)
            phase = checkpoint["phase"]
        if phase == "QUALIFYING":
            checkpoint = self._qualify(ctx, ops, checkpoint)
        if not checkpoint.get("company_ids"):
            # honesty rule: a run that discovered nothing is PARTIAL_SUCCESS,
            # never a silent green READY_FOR_REVIEW
            return "PARTIAL_SUCCESS"
        with ops.uow() as tx:
            tx.repos.acquisition.set_campaign_state(ctx.campaign_id or "", "READY_FOR_REVIEW")
        return "READY_FOR_REVIEW"

    # ------------------------------------------------------------------
    def _cancelled(self, ctx: JobContext, ops: JobOps) -> bool:
        if ops.cancel_requested():
            if ops.apply_cancellation():
                ops.finish_cancelled()
            return True
        return False

    def _plan(self, ctx: JobContext, ops: JobOps) -> dict[str, Any]:
        ops.set_phase("PLANNING")
        with ops.uow() as tx:
            campaign = tx.repos.acquisition.get_campaign(ctx.campaign_id or "")
            if campaign is None:
                raise DomainError("campaign not found for this job")
            icp = tx.repos.acquisition.get_icp_definition(ctx.payload["icp_version_id"])
            if icp is None:
                raise DomainError("icp version not found")

            rules = tx.repos.governance.get_policy_rules() or default_rules()
            decision, basis, reason = evaluate(
                rules, PolicyInput(operation="discovery.search", country=icp.get("country")),
            )
            tx.repos.governance.record_decision(
                "campaign", ctx.campaign_id or "", "discovery.search",
                decision.value, POLICY_VERSION, basis, reason, ctx.worker_id or "worker",
            )
            tx.emit(EventEnvelope(
                type=POLICY_DECISION_RECORDED, aggregate_type="campaign",
                aggregate_id=ctx.campaign_id or "", org_id=ctx.org_id,
                payload={"operation": "discovery.search", "decision": decision.value},
            ))
            if decision is GovernanceDecision.BLOCKED:
                raise DomainError(f"policy blocked discovery: {reason}")

        plan = build_query_plan(icp)
        if is_empty_plan(plan):
            raise DomainError(
                "ICP produced zero queries — add cities/keywords instead of silently doing nothing"
            )
        checkpoint = {
            "phase": "DISCOVERING",
            "queries": plan["queries"],
            "results_per_query": plan["results_per_query"],
            "query_index": 0,
            "company_ids": [],
            "icp_country": icp.get("country"),
            "icp_industry": icp.get("industry"),
            "icp_version_id": ctx.payload.get("icp_version_id"),
            "budget_cents": int(ctx.payload.get("budget_cents", 0)),
        }
        ops.checkpoint(checkpoint, state="DISCOVERING")
        return checkpoint

    # ------------------------------------------------------------------
    def _discover(self, ctx: JobContext, ops: JobOps, ck: dict[str, Any]) -> dict[str, Any]:
        company_ids: list[str] = list(ck.get("company_ids", []))
        index = int(ck.get("query_index", 0))
        queries = ck["queries"]

        while index < len(queries):
            if self._cancelled(ctx, ops):
                return {**ck, "phase": "CANCELLING"}
            entry = queries[index]
            with ops.uow() as tx:
                result = ops.gateway.execute(
                    tx.cursor, ctx.org_id, Capability.SEARCH_COMPANIES,
                    operation="search_companies",
                    params={"query": entry["q"], "max_results": ck["results_per_query"]},
                    job_id=ctx.job_id,
                    budget_cents=ck.get("budget_cents") or None,
                )
                if not result.ok:
                    log.warning("search failed (%s): %s", result.failure, result.error)
                else:
                    for raw in result.data.get("results", []):
                        company_id = self._ingest_result(tx, ctx, ck, entry, raw)
                        if company_id and company_id not in company_ids:
                            company_ids.append(company_id)
            ops.heartbeat()
            index += 1
            ck = {**ck, "query_index": index, "company_ids": company_ids}
            ops.checkpoint(ck)

        ops.checkpoint({**ck, "phase": "ENRICHING", "enrich_index": 0}, state="ENRICHING")
        return {**ck, "phase": "ENRICHING"}

    def _ingest_result(self, tx, ctx: JobContext, ck: dict[str, Any],
                       entry: dict[str, str], raw: dict[str, Any]) -> str | None:
        url = str(raw.get("url") or "")
        title = str(raw.get("title") or "")
        if not url:
            return None
        if not tx.repos.intelligence.add_raw_result(ctx.job_id, "gateway", entry["q"],
                                                    url, title, raw.get("snippet")):
            return None  # duplicate for this job
        if not tx.repos.intelligence.mark_visited(ctx.job_id, url):
            return None  # already processed by an earlier attempt (idempotent resume)

        domain = domain_from_url(url)
        known_by_domain = bool(domain and tx.repos.companies.find_by_domain(domain))
        known_by_name = bool(tx.repos.companies.find_by_normalized_name(normalize_name(title)))
        kind = resolve_identity(title, url, known_by_domain, known_by_name)
        if kind in ("social", "editorial"):
            return None

        if kind == "existing":
            company = (tx.repos.companies.find_by_domain(domain) if domain else None) \
                or tx.repos.companies.find_by_normalized_name(normalize_name(title))
            company_id = str(company["id"])
        else:
            company_id = str(uuid4())
            tx.repos.companies.create_company(
                company_id, normalize_name(title) or title, domain,
                ck.get("icp_country"), ck.get("icp_industry"), entry.get("city"),
            )
        if domain:
            tx.repos.companies.add_identifier(company_id, "domain", domain)

        source_id = tx.repos.claims.get_or_create_source(
            "search_result", url, str(raw.get("provider", "search")), _sha(url + title),
        )
        tx.repos.claims.add_observation(company_id, "website", url, source_id, "snippet", 0.6)
        tx.repos.claims.add_observation(company_id, "name", title, source_id, "snippet", 0.6)
        tx.repos.claims.upsert_claim(company_id, "website", url, source_id, "snippet", 0.6)
        if entry.get("city"):
            tx.repos.claims.upsert_claim(company_id, "city", entry["city"], source_id,
                                         "icp_plan", 0.9)

        # contacts visible in the snippet itself (legacy-proven signal)
        found = extract_contacts(f"{title} {raw.get('snippet', '')}")
        for email in found["emails"]:
            contact_id = tx.repos.contacts.find_or_create_contact(
                company_id, normalize_name(title) or title, "contact", source_id)
            ref = tx.vault.store("email", email)
            tx.repos.contacts.attach_email_ref(contact_id, ref)
            tx.repos.claims.add_observation(
                company_id, "contact_email_masked", tx.vault.masked("email", email),
                source_id, "snippet", 0.7)
        for phone in found["phones"]:
            contact_id = tx.repos.contacts.find_or_create_contact(
                company_id, normalize_name(title) or title, "contact", source_id)
            ref = tx.vault.store("phone", phone)
            tx.repos.contacts.attach_phone_ref(contact_id, ref)
        return company_id

    # ------------------------------------------------------------------
    def _enrich(self, ctx: JobContext, ops: JobOps, ck: dict[str, Any]) -> dict[str, Any]:
        company_ids = list(ck.get("company_ids", []))
        index = int(ck.get("enrich_index", 0))

        while index < len(company_ids):
            if self._cancelled(ctx, ops):
                return {**ck, "phase": "CANCELLING"}
            company_id = company_ids[index]
            with ops.uow() as tx:
                company = tx.repos.intelligence.company_context(company_id)
                result = ops.gateway.execute(
                    tx.cursor, ctx.org_id, Capability.FIND_CONTACT,
                    operation="find_contact",
                    params={"company": company["canonical_name"], "domain": company.get("domain")},
                    job_id=ctx.job_id,
                    budget_cents=ck.get("budget_cents") or None,
                )
                if result.ok:
                    self._store_contacts(tx, company_id, result.data)
                    tx.repos.intelligence.record_enrichment(
                        company_id, "gateway", "find_contact", "ok",
                        cost_cents=result.cost_cents)
                else:
                    tx.repos.intelligence.record_enrichment(
                        company_id, "gateway", "find_contact", "failed",
                        failure_class=result.failure.value if result.failure else None)
            ops.heartbeat()
            index += 1
            ck = {**ck, "enrich_index": index}
            ops.checkpoint(ck)

        ops.checkpoint({**ck, "phase": "VERIFYING", "verify_index": 0}, state="VERIFYING")
        return {**ck, "phase": "VERIFYING"}

    def _store_contacts(self, tx, company_id: str, data: dict[str, Any]) -> None:
        for person in data.get("contacts", []):
            contact_id = tx.repos.contacts.find_or_create_contact(
                company_id, person.get("name"), person.get("role"), None)
            email = person.get("email")
            if email:
                ref = tx.vault.store("email", email)
                tx.repos.contacts.attach_email_ref(contact_id, ref)
                tx.repos.claims.add_observation(
                    company_id, "contact_email_masked", tx.vault.masked("email", email),
                    None, "enrichment", 0.7)
            phone = person.get("phone")
            if phone:
                ref = tx.vault.store("phone", phone)
                tx.repos.contacts.attach_phone_ref(contact_id, ref)
            if person.get("social"):
                tx.repos.contacts.attach_social(contact_id, str(person["social"]))

    # ------------------------------------------------------------------
    def _verify(self, ctx: JobContext, ops: JobOps, ck: dict[str, Any]) -> dict[str, Any]:
        company_ids = list(ck.get("company_ids", []))
        index = int(ck.get("verify_index", 0))

        while index < len(company_ids):
            if self._cancelled(ctx, ops):
                return {**ck, "phase": "CANCELLING"}
            company_id = company_ids[index]
            with ops.uow() as tx:
                for contact in tx.repos.contacts.list_company_contacts(company_id):
                    email_ref = contact.get("email_ref")
                    if not email_ref:
                        continue
                    email = tx.vault.decrypt(str(email_ref), "verification",
                                             actor=ctx.worker_id or "worker",
                                             request_id=ctx.job_id)
                    cache_key = _sha(email)
                    cached = tx.repos.intelligence.get_cached_verification(cache_key)
                    if cached:
                        status, evidence, provider_id = cached["status"], cached["evidence"], "cache"
                    else:
                        result = ops.gateway.execute(
                            tx.cursor, ctx.org_id, Capability.VERIFY_EMAIL,
                            operation="verify_email", params={"email": email},
                            job_id=ctx.job_id,
                            budget_cents=ck.get("budget_cents") or None,
                        )
                        if not result.ok:
                            status, evidence, provider_id = "UNKNOWN", {}, "gateway"
                        else:
                            status = result.data.get("status", "UNKNOWN")
                            evidence = {k: v for k, v in result.data.items() if k != "status"}
                            provider_id = "gateway"
                            tx.repos.intelligence.cache_verification(
                                cache_key, status, evidence,
                                datetime.now(timezone.utc) + timedelta(days=7))
                    status = promote(VerificationStatus.UNKNOWN, VerificationStatus(status), evidence)
                    tx.repos.intelligence.record_verification(
                        str(contact["id"]), "email", str(email_ref), status, provider_id, evidence)
                    tx.emit(EventEnvelope(
                        type=VERIFICATION_COMPLETED, aggregate_type="contact",
                        aggregate_id=str(contact["id"]), org_id=ctx.org_id,
                        payload={"status": status, "company_id": company_id},
                    ))
            ops.heartbeat()
            index += 1
            ck = {**ck, "verify_index": index}
            ops.checkpoint(ck)

        ops.checkpoint({**ck, "phase": "SCORING", "score_index": 0}, state="SCORING")
        return {**ck, "phase": "SCORING"}

    # ------------------------------------------------------------------
    def _score(self, ctx: JobContext, ops: JobOps, ck: dict[str, Any]) -> dict[str, Any]:
        company_ids = list(ck.get("company_ids", []))
        index = int(ck.get("score_index", 0))

        while index < len(company_ids):
            company_id = company_ids[index]
            with ops.uow() as tx:
                summary = tx.repos.claims.claims_summary(company_id)
                best: VerificationStatus | None = None
                for contact in tx.repos.contacts.list_company_contacts(company_id):
                    if not contact.get("email_ref"):
                        continue
                    email = tx.vault.decrypt(str(contact["email_ref"]), "verification",
                                             actor=ctx.worker_id or "worker",
                                             request_id=ctx.job_id)
                    cached = tx.repos.intelligence.get_cached_verification(_sha(email))
                    if cached:
                        best = _best_status(best, VerificationStatus(cached["status"]))
                inputs = ScoreInputs(
                    has_website=bool(summary.get("website")),
                    observation_count=int(summary.get("_observations", 0)),
                    distinct_source_count=int(summary.get("_distinct_sources", 0)),
                    best_email_status=best,
                    icp_city_match=bool(summary.get("city")),
                )
                scored = compute_score(inputs)
                ai_note = None
                if ops.model_gateway is not None:
                    try:
                        reply = ops.model_gateway.complete(
                            "reasoning",
                            "اقترح تفسيرًا قصيرًا بالعربية (سطر واحد) لدرجة تأهيل شركة "
                            f"بها: موقع={inputs.has_website}، مصادر={inputs.distinct_source_count}، "
                            f"ملاحظات={inputs.observation_count}، بريد={best.value if best else 'none'}، "
                            f"الدرجة={scored.score}. اذكر لماذا تستحق المراجعة أو القبول. "
                            "ممنوع ذكر أي بيانات شخصية.")
                        ai_note = reply.text[:400]
                    except Exception as exc:  # noqa: BLE001 — AI is advisory only
                        ai_note = None
                        del exc
                tx.repos.intelligence.add_scoring_record(
                    company_id, scored.score, scored.version,
                    {"best_email_status": best.value if best else None,
                     "has_website": inputs.has_website,
                     "observations": inputs.observation_count,
                     "sources": inputs.distinct_source_count,
                     "ai_note": ai_note},
                    scored.explanations + ([f"ai: {ai_note}"] if ai_note else []),
                )
            index += 1
            ck = {**ck, "score_index": index}
            ops.checkpoint(ck)

        ops.checkpoint({**ck, "phase": "QUALIFYING", "qualify_index": 0}, state="QUALIFYING")
        return {**ck, "phase": "QUALIFYING"}

    # ------------------------------------------------------------------
    def _qualify(self, ctx: JobContext, ops: JobOps, ck: dict[str, Any]) -> dict[str, Any]:
        company_ids = list(ck.get("company_ids", []))
        rules = None
        for company_id in company_ids:
            with ops.uow() as tx:
                company = tx.repos.intelligence.company_context(company_id)
                summary = tx.repos.claims.claims_summary(company_id)
                contacts = tx.repos.contacts.list_company_contacts(company_id)

                email_status: VerificationStatus | None = None
                email_plain: str | None = None
                phone_plain: str | None = None
                for contact in contacts:
                    if contact.get("email_ref") and email_plain is None:
                        email_plain = tx.vault.decrypt(str(contact["email_ref"]),
                                                       "human_review",
                                                       actor=ctx.worker_id or "worker",
                                                       request_id=ctx.job_id)
                        cached = tx.repos.intelligence.get_cached_verification(_sha(email_plain))
                        if cached:
                            email_status = _best_status(email_status,
                                                        VerificationStatus(cached["status"]))
                    if contact.get("phone_ref") and phone_plain is None:
                        phone_plain = tx.vault.decrypt(str(contact["phone_ref"]),
                                                       "human_review",
                                                       actor=ctx.worker_id or "worker",
                                                       request_id=ctx.job_id)

                rules = rules or tx.repos.governance.get_policy_rules() or default_rules()
                domain = company.get("domain")
                suppressed = tx.repos.governance.is_suppressed("domain", domain or "")
                policy_decision, _, _ = evaluate(
                    rules, PolicyInput(operation="lead.qualification",
                                       country=ck.get("icp_country")),
                )
                score = tx.repos.intelligence.latest_score(company_id)
                decision, reasons = decide(QualificationInputs(
                    score=score, domain=domain, email_status=email_status,
                    suppressed=suppressed, policy_decision=policy_decision.value,
                    country=ck.get("icp_country"),
                ))
                tx.repos.intelligence.add_qualification_record(
                    company_id, ctx.campaign_id, decision.value, reasons,
                    ck.get("icp_version_id"), POLICY_VERSION,
                )
                if decision is QualificationDecision.REJECTED:
                    continue
                lead_id = tx.repos.projects.upsert_lead(
                    campaign_id=ctx.campaign_id, company_id=company_id,
                    contact_id=str(contacts[0]["id"]) if contacts else None,
                    icp_version_id=ck.get("icp_version_id"),
                    display={"name": company["canonical_name"], "domain": domain,
                             "city": summary.get("city"),
                             "industry": company.get("industry")},
                    masked_email=tx.vault.masked("email", email_plain) if email_plain else None,
                    masked_phone=tx.vault.masked("phone", phone_plain) if phone_plain else None,
                    email_status=email_status.value if email_status else None,
                    score=score, score_version="v1", decision=decision.value,
                )
                tx.emit(EventEnvelope(
                    type=LEAD_READY_FOR_REVIEW, aggregate_type="lead",
                    aggregate_id=lead_id, org_id=ctx.org_id,
                    payload={"company_id": company_id, "decision": decision.value,
                             "score": score},
                ))
        return {**ck, "phase": "DONE"}
