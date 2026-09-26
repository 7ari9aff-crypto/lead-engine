"""Governance, Projects (lead projection) and Lineage repos."""
from __future__ import annotations

from typing import Any

import psycopg

from infrastructure.repos.core import _one, _q


class GovernanceRepo:
    def __init__(self, cur: psycopg.Cursor):
        self.cur = cur

    def get_policy_rules(self) -> dict[str, Any]:
        row = _one(
            self.cur,
            """SELECT rules FROM governance.legal_policy_versions
               WHERE org_id = current_setting('app.tenant_id', true)::uuid
               ORDER BY published_at DESC LIMIT 1""",
        )
        return row["rules"] if row else {}

    def record_decision(self, subject_type: str, subject_id: str, operation: str,
                        decision: str, policy_version: str, legal_basis: str,
                        decision_reason: str, decided_by: str) -> str:
        row = _one(
            self.cur,
            """INSERT INTO governance.legal_decisions
                 (org_id, subject_type, subject_id, operation, decision, policy_version,
                  legal_basis, decision_reason, decided_by)
               VALUES (current_setting('app.tenant_id', true)::uuid, %s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (subject_type, subject_id, operation, decision, policy_version,
             legal_basis, decision_reason, decided_by),
        )
        return str(row["id"])

    def is_suppressed(self, kind: str, value: str) -> bool:
        return _one(
            self.cur,
            """SELECT 1 AS hit FROM governance.suppression
               WHERE org_id = current_setting('app.tenant_id', true)::uuid
                 AND kind = %s AND value = %s LIMIT 1""",
            (kind, value.lower()),
        ) is not None

    def add_suppression(self, kind: str, value: str, reason: str) -> None:
        self.cur.execute(
            """INSERT INTO governance.suppression (org_id, kind, value, reason)
               VALUES (current_setting('app.tenant_id', true)::uuid, %s, %s, %s)
               ON CONFLICT (org_id, kind, value) DO NOTHING""",
            (kind, value.lower(), reason),
        )


class ProjectsRepo:
    def __init__(self, cur: psycopg.Cursor):
        self.cur = cur

    def upsert_lead(self, campaign_id: str | None, company_id: str, contact_id: str | None,
                    icp_version_id: str | None, display: dict[str, Any],
                    masked_email: str | None, masked_phone: str | None,
                    email_status: str | None, score: float | None,
                    score_version: str | None, decision: str) -> str:
        row = _one(
            self.cur,
            """INSERT INTO projects.lead_projections
                 (org_id, campaign_id, company_id, contact_id, icp_version_id, display,
                  masked_email, masked_phone, email_status, score, score_version, decision)
               VALUES (current_setting('app.tenant_id', true)::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (org_id, campaign_id, company_id, contact_id) DO UPDATE SET
                 display = EXCLUDED.display, masked_email = EXCLUDED.masked_email,
                 masked_phone = EXCLUDED.masked_phone, email_status = EXCLUDED.email_status,
                 score = EXCLUDED.score, score_version = EXCLUDED.score_version,
                 decision = EXCLUDED.decision, built_at = now()
               RETURNING id""",
            (campaign_id, company_id, contact_id, icp_version_id,
             psycopg.types.json.Json(display), masked_email, masked_phone, email_status,
             score, score_version, decision),
        )
        return str(row["id"])

    def list_leads(self, state: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        base = """SELECT * FROM projects.lead_projections
                  WHERE org_id = current_setting('app.tenant_id', true)::uuid"""
        if state:
            return _q(self.cur, base + " AND state = %s ORDER BY built_at DESC LIMIT %s",
                      (state, limit))
        return _q(self.cur, base + " ORDER BY built_at DESC LIMIT %s", (limit,))

    def get_lead(self, lead_id: str) -> dict[str, Any] | None:
        return _one(
            self.cur,
            """SELECT * FROM projects.lead_projections
               WHERE org_id = current_setting('app.tenant_id', true)::uuid AND id = %s""",
            (lead_id,),
        )

    def decide_lead(self, lead_id: str, state: str, decided_by: str) -> bool:
        row = _one(
            self.cur,
            """UPDATE projects.lead_projections
               SET state = %s,
                   built_from = built_from || jsonb_build_object('decided_by', %s::text,
                                 'decided_at', now()::text)
               WHERE org_id = current_setting('app.tenant_id', true)::uuid AND id = %s
                 AND state = 'READY_FOR_REVIEW'
               RETURNING id""",
            (state, decided_by, lead_id),
        )
        return row is not None


class LineageRepo:
    """Business lineage: answers 'why is this lead here?' by joining every
    authoritative record from discovery to decision (architecture §28)."""

    def __init__(self, cur: psycopg.Cursor):
        self.cur = cur

    def lead_lineage(self, lead_id: str) -> dict[str, Any]:
        lead = _one(
            self.cur,
            """SELECT * FROM projects.lead_projections
               WHERE org_id = current_setting('app.tenant_id', true)::uuid AND id = %s""",
            (lead_id,),
        )
        if not lead:
            return {}
        company_id = lead["company_id"]
        qualifications = _q(
            self.cur,
            """SELECT decision, reasons, created_at FROM intelligence.qualification_records
               WHERE org_id = current_setting('app.tenant_id', true)::uuid AND company_id = %s
               ORDER BY created_at DESC LIMIT 5""",
            (company_id,),
        )
        scores = _q(
            self.cur,
            """SELECT score, score_version, explanations, created_at
               FROM intelligence.scoring_records
               WHERE org_id = current_setting('app.tenant_id', true)::uuid AND company_id = %s
               ORDER BY created_at DESC LIMIT 5""",
            (company_id,),
        )
        claims = _q(
            self.cur,
            """SELECT field, value, source_id, truth_state, confidence
               FROM claims_evidence.company_claims
               WHERE org_id = current_setting('app.tenant_id', true)::uuid AND company_id = %s""",
            (company_id,),
        )
        sources = _q(
            self.cur,
            """SELECT DISTINCT s.id, s.kind, s.url, s.provider_id, s.fetched_at
               FROM claims_evidence.fact_sources s
               JOIN claims_evidence.company_claims c
                 ON c.source_id = s.id
                AND c.org_id = s.org_id
               WHERE s.org_id = current_setting('app.tenant_id', true)::uuid
                 AND c.company_id = %s""",
            (company_id,),
        )
        verifications = _q(
            self.cur,
            """SELECT v.status, v.provider_id, v.verified_at
               FROM intelligence.verification_records v
               JOIN contacts.company_contacts c ON c.id = v.contact_id
               WHERE v.org_id = current_setting('app.tenant_id', true)::uuid
                 AND c.company_id = %s
               ORDER BY v.verified_at DESC LIMIT 10""",
            (company_id,),
        )
        provider_calls = _q(
            self.cur,
            """SELECT provider_id, operation, status, cost_cents, created_at
               FROM effects.effect_ledger
               WHERE org_id = current_setting('app.tenant_id', true)::uuid
                 AND job_id = %s
               ORDER BY created_at DESC LIMIT 20""",
            (lead.get("campaign_id"),),
        )
        return {
            "lead": {k: lead[k] for k in ("id", "state", "decision", "score", "built_at")},
            "qualification": qualifications,
            "scores": scores,
            "claims": claims,
            "sources": sources,
            "verifications": verifications,
            "provider_calls": provider_calls,
        }
