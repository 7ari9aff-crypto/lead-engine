"""Supabase sync — maps engine output onto the existing 'lead' project schema.

Engine → Supabase mapping (existing live schema, CHECK-constrained):
  ICP + job        → campaigns (ACTIVE) + icp_profiles
  engine state     → jobs.status (QUEUED/RUNNING/DEGRADED/PAUSED/RESUMING/COMPLETED/FAILED)
  usage_ledger     → job_resource_usage (task_kind: DISCOVERY/ENRICH/RESEARCH/QUALIFY/VERIFY)
  deduped lead     → companies (upsert by normalized_domain, else dedup_name+city)
                     + company_claims + company_observations + company_contacts
  email_status     → contact_verifications (DELIVERABLE→VALID, CATCH_ALL→RISKY+detail)
  stage            → leads.status  (ACCEPTED→QUALIFIED, REVIEW→REVIEW, REJECTED→REJECTED)
  legal decision   → leads.legal_status (ACCEPTED→ALLOWED, REJECTED→BLOCKED, REVIEW→REVIEW)

Lookup notes: this project's PostgREST does not match quoted filter values,
so text lookups use ilike wildcards and are verified exact client-side.
Env: SUPABASE_URL + SUPABASE_SERVICE_KEY (service role bypasses RLS).
"""
import json
import os
import re

import requests

from .pipeline.normalize import normalize_text

VERIFY_MAP = {"DELIVERABLE": "VALID", "RISKY": "RISKY", "CATCH_ALL": "RISKY",
              "INVALID": "INVALID", "UNKNOWN": "UNKNOWN"}
LEAD_STATUS_MAP = {"ACCEPTED": "QUALIFIED", "REVIEW": "REVIEW", "REJECTED": "REJECTED"}
LEGAL_STATUS_MAP = {"ACCEPTED": "ALLOWED", "REVIEW": "REVIEW", "REJECTED": "BLOCKED"}
TASK_KIND_MAP = {"web_search": "DISCOVERY", "people_search": "DISCOVERY",
                 "org_search": "RESEARCH", "enrichment": "ENRICH",
                 "reasoning": "QUALIFY", "inference": "QUALIFY",
                 "email_verify": "VERIFY", "email_find": "RESEARCH"}
PROVIDER_KIND_MAP = {"search": "SEARCH", "llm": "LLM", "data": "DATA", "email": "EMAIL"}
PROVIDER_TASKS_MAP = {"web_search": ["DISCOVERY", "RESEARCH"],
                      "reasoning": ["QUALIFY"], "inference": ["QUALIFY"],
                      "people_search": ["DISCOVERY", "RESEARCH"],
                      "org_search": ["RESEARCH"], "enrichment": ["ENRICH"],
                      "email_verify": ["VERIFY"], "email_find": ["RESEARCH"]}


class SupabaseError(RuntimeError):
    pass


def eq(value) -> str:
    """Filter for parser-safe tokens (uuids, domains, emails): sent bare.
    Anything else must go through ilike + client-side exact check."""
    return f"eq.{value}"


def ilike_pattern(value: str) -> str:
    """Wildcard pattern for values that cannot be sent bare (spaces, '::')."""
    value = str(value)
    return re.sub(r"[ :()\[\]\"']", "*", value) or "*"


class Rest:
    """Tiny PostgREST client."""

    def __init__(self):
        url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        key = os.environ.get("SUPABASE_SERVICE_KEY", "")
        if not url or not key:
            raise SupabaseError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env")
        self.base = f"{url}/rest/v1"
        self.headers = {"apikey": key, "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                        "Prefer": "return=representation"}

    def _check(self, resp):
        if resp.status_code >= 400:
            raise SupabaseError(f"{resp.request.method} {resp.request.url} -> "
                                f"{resp.status_code}: {resp.text[:300]}")
        return resp

    @staticmethod
    def _qs(params: dict) -> str:
        from urllib.parse import quote

        return "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params.items())

    def select(self, table: str, params: dict) -> list:
        resp = self._check(requests.get(f"{self.base}/{table}?{self._qs(params)}",
                                        headers=self.headers, timeout=30))
        return resp.json()

    def insert(self, table: str, rows: list) -> list:
        resp = self._check(requests.post(f"{self.base}/{table}",
                                         headers=self.headers, json=rows, timeout=30))
        return resp.json() if resp.text else []

    def update(self, table: str, params: dict, payload: dict) -> list:
        resp = self._check(requests.patch(f"{self.base}/{table}?{self._qs(params)}",
                                          headers=self.headers,
                                          json=payload, timeout=30))
        return resp.json() if resp.text else []

    def find_exact(self, table: str, field: str, value: str, extra: dict = None):
        """ilike lookup + exact client-side verification (quoted eq is not
        supported by this project's PostgREST)."""
        params = {field: f"ilike.{ilike_pattern(value)}"}
        params.update(extra or {})
        for row in self.select(table, params):
            if str(row.get(field) or "").strip() == str(value).strip():
                return row
        return None


def sync_job_to_supabase(db, engine_job_id: str) -> dict:
    """Push one completed engine job into Supabase. Idempotent per job."""
    rest = Rest()
    job = db.one("SELECT * FROM jobs WHERE job_id=?", (engine_job_id,))
    if not job:
        raise SupabaseError(f"unknown engine job {engine_job_id}")
    leads = db.leads_for_job(engine_job_id)
    usage = db.query("SELECT provider, task, units FROM usage_ledger WHERE job_id=?",
                     (engine_job_id,))
    icp = _load_icp_for(db, engine_job_id)

    campaign_name = f"{job['icp_id']}::{engine_job_id}"
    campaign = rest.find_exact("campaigns", "name", campaign_name)
    campaign_payload = {
        "name": campaign_name,
        "icp_text": json.dumps(icp, ensure_ascii=False),
        "status": "ACTIVE",
        "budgets": {"enrichment_budget_credits":
                    (icp.get("v0_limits", {}) or {}).get("enrichment_budget_credits", 50)},
    }
    if campaign:
        campaign_id = rest.update("campaigns", {"id": eq(campaign["id"])},
                                  campaign_payload)[0]["id"]
    else:
        campaign_id = rest.insert("campaigns", [campaign_payload])[0]["id"]

    if not rest.select("icp_profiles", {"campaign_id": eq(campaign_id)}):
        rest.insert("icp_profiles", [{
            "campaign_id": campaign_id,
            "raw_text": json.dumps(icp, ensure_ascii=False),
            "constraints": {
                "cities": [c["name"] for c in icp.get("cities", [])],
                "industry": icp.get("industry"),
                "min_branches": (icp.get("criteria", {}) or {}).get("min_branches"),
                "decision_maker_roles": (icp.get("criteria", {}) or {}).get("decision_maker_roles", []),
            },
        }])

    counts = _counts(leads)
    job_row = rest.select("jobs", {"campaign_id": eq(campaign_id),
                                   "order": "created_at.desc", "limit": "1"})
    job_payload = {
        "status": job["state"],
        "discovered": counts["discovered"],
        "qualified": counts["qualified"],
        "rejected": counts["rejected"],
        "degraded_reason": "local LLM used" if counts["degraded"] else None,
    }
    if job["state"] in ("COMPLETED", "FAILED"):
        job_payload["finished_at"] = "now()"
    if job_row:
        supa_job_id = rest.update("jobs", {"id": eq(job_row[0]["id"])}, job_payload)[0]["id"]
    else:
        supa_job_id = rest.insert("jobs", [{**job_payload, "campaign_id": campaign_id}])[0]["id"]

    provider_ids = _sync_providers(rest, db)

    if usage:
        rest.insert("job_resource_usage", [{
            "job_id": supa_job_id,
            "provider_id": provider_ids.get(u["provider"]),
            "task_kind": TASK_KIND_MAP.get(u["task"], "RESEARCH"),
            "units": int(u["units"] or 0),
        } for u in usage if TASK_KIND_MAP.get(u["task"])])

    synced = {"companies": 0, "contacts": 0, "leads": 0, "verifications": 0}
    for lead in leads:
        company_id = _sync_company(rest, lead)
        synced["companies"] += 1
        if lead.get("snippet"):
            rest.insert("company_observations", [{
                "company_id": company_id,
                "source_url": (lead.get("source_urls") or [None])[0],
                "source_type": "search_api",
                "extraction_method": "web_search",
                "raw": {"snippet": lead.get("snippet"),
                        "queries": lead.get("source_queries") or []},
            }])
        _sync_claims(rest, company_id, lead)
        contact_id = _sync_contact(rest, company_id, lead)
        if contact_id:
            synced["contacts"] += 1
            synced["verifications"] += _sync_verification(rest, contact_id, lead)
        _sync_lead(rest, campaign_id, company_id, contact_id, lead)
        synced["leads"] += 1
    synced["job_id"] = supa_job_id
    synced["campaign_id"] = campaign_id
    return synced


def _load_icp_for(db, engine_job_id):
    from .config import load_icp

    job = db.one("SELECT icp_id FROM jobs WHERE job_id=?", (engine_job_id,))
    try:
        return load_icp(job["icp_id"])
    except Exception:
        return {}


def _counts(leads):
    return {
        "discovered": len(leads),
        "qualified": sum(1 for l in leads if l.get("stage") == "ACCEPTED"),
        "rejected": sum(1 for l in leads if l.get("stage") == "REJECTED"),
        "degraded": any(l.get("processing_mode") == "degraded_local" for l in leads),
    }


def _sync_providers(rest: Rest, db) -> dict:
    ids = {row["name"]: row["id"]
           for row in rest.select("providers", {"select": "id,name"})}
    for prow in db.query("SELECT name, type, task, priority, env_key FROM providers"):
        if prow["name"] in ids:
            continue
        created = rest.insert("providers", [{
            "name": prow["name"],
            "kind": PROVIDER_KIND_MAP.get(prow["type"], "DATA"),
            "supported_tasks": PROVIDER_TASKS_MAP.get(prow["task"], []),
            "priority": prow["priority"] * 10,
            "api_key_env": prow["env_key"],
        }])
        ids[prow["name"]] = created[0]["id"]
    return ids


def _sync_company(rest: Rest, lead: dict) -> str:
    domain = (lead.get("domain") or "").lower() or None
    existing = None
    if domain:
        rows = rest.select("companies", {"normalized_domain": eq(domain), "limit": "1"})
        existing = rows[0] if rows else None
    if existing is None:
        name_key = normalize_text(lead.get("name"))
        if name_key:
            existing = rest.find_exact("companies", "dedup_name", name_key)

    payload = {
        "canonical_name": lead.get("name") or domain or "unknown",
        "dedup_name": normalize_text(lead.get("name")) or None,
        "domain": lead.get("domain"),
        "normalized_domain": domain,
        "country": lead.get("country"),
        "city": lead.get("city"),
        "industry": lead.get("industry"),
        "branches": lead.get("branches"),
        "data": {
            "score": lead.get("score"), "tier": lead.get("tier"),
            "qualification_score": lead.get("qualification_score"),
            "processing_mode": lead.get("processing_mode"),
            "website": lead.get("website"), "social": lead.get("social"),
            "snippet": lead.get("snippet"),
            "engine_lead_id": lead.get("lead_id"),
        },
    }
    if existing:
        return rest.update("companies", {"id": eq(existing["id"])}, payload)[0]["id"]
    return rest.insert("companies", [payload])[0]["id"]


def _sync_contact(rest: Rest, company_id: str, lead: dict):
    if not (lead.get("decision_maker") or lead.get("email") or lead.get("phone")):
        return None
    email = (lead.get("email") or "").lower() or None
    existing = None
    if email:
        rows = rest.select("company_contacts", {"company_id": eq(company_id),
                                                "email": eq(email), "limit": "1"})
        existing = rows[0] if rows else None
    if existing is None and lead.get("decision_maker"):
        existing = rest.find_exact("company_contacts", "name", lead["decision_maker"],
                                   {"company_id": eq(company_id)})
    payload = {
        "company_id": company_id,
        "name": lead.get("decision_maker"),
        "title": lead.get("decision_maker_title"),
        "email": email,
        "phone": lead.get("phone"),
        "linkedin_url": lead.get("linkedin"),
        "is_decision_maker": bool(lead.get("decision_maker")),
    }
    if existing:
        return rest.update("company_contacts", {"id": eq(existing["id"])}, payload)[0]["id"]
    return rest.insert("company_contacts", [payload])[0]["id"]


def _sync_verification(rest: Rest, contact_id: str, lead: dict) -> int:
    status = lead.get("email_status")
    if not status:
        return 0
    rest.insert("contact_verifications", [{
        "contact_id": contact_id,
        "channel": "email",
        "status": VERIFY_MAP.get(status, "UNKNOWN"),
        "detail": {"engine_status": status, "confidence": lead.get("email_confidence")},
    }])
    return 1


def _sync_lead(rest: Rest, campaign_id, company_id, contact_id, lead: dict):
    stage = lead.get("stage", "REVIEW")
    sources = lead.get("source_urls") or []
    payload = {
        "campaign_id": campaign_id,
        "company_id": company_id,
        "contact_id": contact_id,
        "status": LEAD_STATUS_MAP.get(stage, "REVIEW"),
        "icp_score": lead.get("qualification_score"),
        "score_breakdown": {"composite": lead.get("score"),
                            "email_confidence": lead.get("email_confidence")},
        "qualification": {"tier": lead.get("tier"),
                          "branches": lead.get("branches"),
                          "processing_mode": lead.get("processing_mode")},
        "legal_status": LEGAL_STATUS_MAP.get(stage, "REVIEW"),
        "legal_reason": lead.get("legal_decision"),
        "evidence_count": len(sources),
    }
    # uq_leads_campaign_company: one lead row per (campaign, company)
    existing = rest.select("leads", {"campaign_id": eq(campaign_id),
                                     "company_id": eq(company_id), "limit": "1"})
    if existing:
        rest.update("leads", {"id": eq(existing[0]["id"])}, payload)
    else:
        rest.insert("leads", [payload])


def _sync_claims(rest: Rest, company_id: str, lead: dict):
    """Idempotent: a (company, kind, value) claim is inserted once.
    Re-syncing the same job no longer inflates company_claims."""
    claims = []
    if lead.get("industry"):
        claims.append({"kind": "INDUSTRY", "value": lead["industry"]})
    if lead.get("city"):
        claims.append({"kind": "LOCATION", "value": lead["city"]})
    if lead.get("branches"):
        claims.append({"kind": "BRANCH_COUNT", "value": str(lead["branches"])})
    if not claims:
        return
    existing = {
        (row.get("kind"), str(row.get("value") or ""))
        for row in rest.select("company_claims", {
            "company_id": eq(company_id), "select": "kind,value"})
    }
    missing = [c for c in claims if (c["kind"], str(c["value"])) not in existing]
    if not missing:
        return
    rest.insert("company_claims", [{
        "company_id": company_id,
        "kind": claim["kind"], "value": claim["value"],
        "source_url": (lead.get("source_urls") or [None])[0],
        "source_type": "search_api",
        "extraction_method": "web_search",
    } for claim in missing])
