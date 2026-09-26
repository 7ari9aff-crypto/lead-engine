"""SQL implementations of the application repository ports.

Every repo receives an open psycopg connection (bound to a tenant-scoped
transaction by the UnitOfWork). No repo opens its own transaction — atomicity
between business mutation and outbox emission is guaranteed by the caller.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg.types.json import Json  # noqa: F401  (also makes psycopg.types.json.* resolvable)


def _q(cur: psycopg.Cursor, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    cur.execute(sql, params)
    return list(cur.fetchall())


def _one(cur: psycopg.Cursor, sql: str, params: tuple = ()) -> dict[str, Any] | None:
    cur.execute(sql, params)
    return cur.fetchone()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ==========================================================================
class PlatformRepo:
    def __init__(self, cur: psycopg.Cursor):
        self.cur = cur

    def get_plan_limits(self, plan_code: str) -> dict[str, Any]:
        row = _one(self.cur, "SELECT limits FROM platform.plans WHERE code = %s", (plan_code,))
        return row["limits"] if row else {}

    def record_usage(self, kind: str, units: float = 0, cost_cents: float = 0,
                     ref: dict[str, Any] | None = None) -> None:
        self.cur.execute(
            """INSERT INTO platform.usage_records (org_id, kind, units, cost_cents, ref)
               VALUES (current_setting('app.tenant_id', true)::uuid, %s, %s, %s, %s)""",
            (kind, units, cost_cents, psycopg.types.json.Json(ref) if ref else None),
        )

    def create_org(self, org_id: str, slug: str, name: str, plan_code: str) -> str:
        row = _one(
            self.cur,
            """INSERT INTO platform.organizations (id, slug, name, plan_code)
               VALUES (%s, %s, %s, %s) RETURNING id""",
            (org_id, slug, name, plan_code),
        )
        return str(row["id"])

    def add_member(self, org_id: str, user_ext_id: str, role: str) -> None:
        self.cur.execute(
            "INSERT INTO platform.members (org_id, user_ext_id, role) VALUES (%s, %s, %s)",
            (org_id, user_ext_id, role),
        )

    def find_membership(self, user_ext_id: str) -> dict[str, Any] | None:
        return _one(
            self.cur,
            """SELECT m.org_id, m.role, o.plan_code, o.slug
               FROM platform.members m JOIN platform.organizations o ON o.id = m.org_id
               WHERE m.user_ext_id = %s LIMIT 1""",
            (user_ext_id,),
        )

    def get_org(self, org_id: str) -> dict[str, Any] | None:
        return _one(self.cur, "SELECT * FROM platform.organizations WHERE id = %s", (org_id,))


# ==========================================================================
class AcquisitionRepo:
    def __init__(self, cur: psycopg.Cursor):
        self.cur = cur

    def create_campaign(self, name: str, icp_version_id: str, budget_cents: int = 0) -> str:
        row = _one(
            self.cur,
            """INSERT INTO acquisition.campaigns (org_id, name, icp_version_id, budget_cents)
               VALUES (current_setting('app.tenant_id', true)::uuid, %s, %s, %s)
               RETURNING id""",
            (name, icp_version_id, budget_cents),
        )
        return str(row["id"])

    def get_campaign(self, campaign_id: str) -> dict[str, Any] | None:
        return _one(
            self.cur,
            "SELECT * FROM acquisition.campaigns WHERE id = %s",
            (campaign_id,),
        )

    def set_campaign_state(self, campaign_id: str, state: str) -> None:
        self.cur.execute(
            "UPDATE acquisition.campaigns SET state = %s, updated_at = now() WHERE id = %s",
            (state, campaign_id),
        )

    def create_icp_version(self, profile_name: str, definition: dict[str, Any]) -> str:
        row = _one(
            self.cur,
            """INSERT INTO acquisition.icp_profiles (org_id, name)
               VALUES (current_setting('app.tenant_id', true)::uuid, %s)
               ON CONFLICT DO NOTHING
               RETURNING id""",
            (profile_name,),
        )
        if row is None:
            row = _one(
                self.cur,
                """SELECT id FROM acquisition.icp_profiles
                   WHERE org_id = current_setting('app.tenant_id', true)::uuid AND name = %s
                   LIMIT 1""",
                (profile_name,),
            )
        profile_id = str(row["id"])
        ver = _one(
            self.cur,
            """SELECT COALESCE(MAX(version), 0) + 1 AS next
               FROM acquisition.icp_versions
               WHERE profile_id = %s""",
            (profile_id,),
        )
        created = _one(
            self.cur,
            """INSERT INTO acquisition.icp_versions
                 (org_id, profile_id, version, definition)
               VALUES (current_setting('app.tenant_id', true)::uuid, %s, %s, %s)
               RETURNING id""",
            (profile_id, ver["next"], psycopg.types.json.Json(definition)),
        )
        return str(created["id"])

    def get_icp_definition(self, version_id: str) -> dict[str, Any] | None:
        row = _one(
            self.cur,
            "SELECT definition FROM acquisition.icp_versions WHERE id = %s",
            (version_id,),
        )
        return row["definition"] if row else None


# ==========================================================================
class CompanyRepo:
    def __init__(self, cur: psycopg.Cursor):
        self.cur = cur

    def find_by_domain(self, domain: str) -> dict[str, Any] | None:
        return _one(
            self.cur,
            """SELECT * FROM company_identity.companies
               WHERE org_id = current_setting('app.tenant_id', true)::uuid
                 AND domain = %s AND merged_into_id IS NULL""",
            (domain,),
        )

    def find_by_normalized_name(self, name: str) -> dict[str, Any] | None:
        return _one(
            self.cur,
            """SELECT * FROM company_identity.companies
               WHERE org_id = current_setting('app.tenant_id', true)::uuid
                 AND lower(canonical_name) = %s AND merged_into_id IS NULL
               LIMIT 1""",
            (name.lower(),),
        )

    def create_company(self, company_id: str, canonical_name: str, domain: str | None,
                       country: str | None, industry: str | None, city: str | None) -> str:
        row = _one(
            self.cur,
            """INSERT INTO company_identity.companies
                 (id, org_id, canonical_name, domain, country, industry, city)
               VALUES (%s, current_setting('app.tenant_id', true)::uuid, %s, %s, %s, %s, %s)
               RETURNING id""",
            (company_id, canonical_name, domain, country, industry, city),
        )
        return str(row["id"])

    def add_identifier(self, company_id: str, kind: str, value: str,
                       source_id: str | None = None) -> None:
        self.cur.execute(
            """INSERT INTO company_identity.company_identifiers
                 (org_id, company_id, kind, value, source_id)
               VALUES (current_setting('app.tenant_id', true)::uuid, %s, %s, %s, %s)
               ON CONFLICT (org_id, kind, value) DO NOTHING""",
            (company_id, kind, value, source_id),
        )


# ==========================================================================
class ClaimsRepo:
    def __init__(self, cur: psycopg.Cursor):
        self.cur = cur

    def get_or_create_source(self, kind: str, url: str | None, provider_id: str | None,
                             content_hash: str | None) -> str:
        if content_hash:
            row = _one(
                self.cur,
                """SELECT id FROM claims_evidence.fact_sources
                   WHERE org_id = current_setting('app.tenant_id', true)::uuid
                     AND content_hash = %s LIMIT 1""",
                (content_hash,),
            )
            if row:
                return str(row["id"])
        row = _one(
            self.cur,
            """INSERT INTO claims_evidence.fact_sources
                 (org_id, kind, url, provider_id, content_hash)
               VALUES (current_setting('app.tenant_id', true)::uuid, %s, %s, %s, %s)
               RETURNING id""",
            (kind, url, provider_id, content_hash),
        )
        return str(row["id"])

    def add_observation(self, company_id: str, field_name: str, value: str | None,
                        source_id: str | None, extraction_method: str,
                        confidence: float) -> None:
        self.cur.execute(
            """INSERT INTO claims_evidence.company_observations
                 (org_id, company_id, field, value, source_id, extraction_method, confidence)
               VALUES (current_setting('app.tenant_id', true)::uuid, %s, %s, %s, %s, %s, %s)""",
            (company_id, field_name, value, source_id, extraction_method, confidence),
        )

    def upsert_claim(self, company_id: str, field_name: str, value: str | None,
                     source_id: str | None, extraction_method: str, confidence: float) -> None:
        existing = _one(
            self.cur,
            """SELECT id, value, confidence FROM claims_evidence.company_claims
               WHERE org_id = current_setting('app.tenant_id', true)::uuid
                 AND company_id = %s AND field = %s
                 AND truth_state IN ('proposed','verified','conflicted')
               FOR UPDATE""",
            (company_id, field_name),
        )
        if existing is None:
            self.cur.execute(
                """INSERT INTO claims_evidence.company_claims
                     (org_id, company_id, field, value, source_id, extraction_method, confidence)
                   VALUES (current_setting('app.tenant_id', true)::uuid, %s, %s, %s, %s, %s, %s)""",
                (company_id, field_name, value, source_id, extraction_method, confidence),
            )
            return
        if existing["value"] != value:
            # Conflict never silently replaces the old claim (architecture §4.4).
            self.cur.execute(
                """INSERT INTO claims_evidence.fact_conflicts
                     (org_id, company_id, field, claim_a_id, claim_b_id)
                   VALUES (current_setting('app.tenant_id', true)::uuid, %s, %s, %s,
                           (SELECT id FROM claims_evidence.company_claims
                             WHERE org_id = current_setting('app.tenant_id', true)::uuid
                               AND company_id = %s AND field = %s AND value = %s LIMIT 1))
                   ON CONFLICT DO NOTHING""",
                (company_id, field_name, existing["id"], company_id, field_name, value),
            )
            self.cur.execute(
                """UPDATE claims_evidence.company_claims SET truth_state = 'conflicted'
                   WHERE id = %s""",
                (existing["id"],),
            )
            self.cur.execute(
                """INSERT INTO claims_evidence.company_claims
                     (org_id, company_id, field, value, source_id, extraction_method, confidence)
                   VALUES (current_setting('app.tenant_id', true)::uuid, %s, %s, %s, %s, %s, %s)""",
                (company_id, field_name, value, source_id, extraction_method, confidence),
            )
        elif confidence > float(existing["confidence"]):
            self.cur.execute(
                """UPDATE claims_evidence.company_claims
                   SET confidence = %s, source_id = COALESCE(%s, source_id)
                   WHERE id = %s""",
                (confidence, source_id, existing["id"]),
            )

    def claims_summary(self, company_id: str) -> dict[str, Any]:
        claims = {
            r["field"]: r["value"]
            for r in _q(
                self.cur,
                """SELECT field, value FROM claims_evidence.company_claims
                   WHERE org_id = current_setting('app.tenant_id', true)::uuid
                     AND company_id = %s
                     AND truth_state IN ('proposed','verified')""",
                (company_id,),
            )
        }
        stats = _one(
            self.cur,
            """SELECT count(*) AS observations,
                      count(DISTINCT source_id) AS distinct_sources
               FROM claims_evidence.company_observations
               WHERE org_id = current_setting('app.tenant_id', true)::uuid AND company_id = %s""",
            (company_id,),
        )
        return {**claims, "_observations": stats["observations"],
                "_distinct_sources": stats["distinct_sources"]}


# ==========================================================================
class ContactsRepo:
    def __init__(self, cur: psycopg.Cursor):
        self.cur = cur

    def find_or_create_contact(self, company_id: str, name: str | None, role: str | None,
                               source_id: str | None) -> str:
        row = _one(
            self.cur,
            """SELECT id FROM contacts.company_contacts
               WHERE org_id = current_setting('app.tenant_id', true)::uuid
                 AND company_id = %s AND lower(name) = lower(%s)
                 AND role IS NOT DISTINCT FROM %s LIMIT 1""",
            (company_id, name or "", role),
        )
        if row:
            return str(row["id"])
        row = _one(
            self.cur,
            """INSERT INTO contacts.company_contacts
                 (org_id, company_id, name, role, source_id)
               VALUES (current_setting('app.tenant_id', true)::uuid, %s, %s, %s, %s)
               RETURNING id""",
            (company_id, name, role, source_id),
        )
        return str(row["id"])

    def _attach(self, contact_id: str, kind: str, public_value: str | None,
                pii_ref_id: str | None) -> None:
        self.cur.execute(
            """INSERT INTO contacts.contact_identities
                 (org_id, contact_id, kind, public_value, pii_ref_id)
               VALUES (current_setting('app.tenant_id', true)::uuid, %s, %s, %s, %s)
               ON CONFLICT (contact_id, kind, public_value, pii_ref_id) DO NOTHING""",
            (contact_id, kind, public_value, pii_ref_id),
        )

    def attach_email_ref(self, contact_id: str, pii_ref_id: str) -> None:
        self._attach(contact_id, "email", None, pii_ref_id)

    def attach_phone_ref(self, contact_id: str, pii_ref_id: str) -> None:
        self._attach(contact_id, "phone", None, pii_ref_id)

    def attach_social(self, contact_id: str, value: str) -> None:
        self._attach(contact_id, "social", value, None)

    def list_company_contacts(self, company_id: str) -> list[dict[str, Any]]:
        return _q(
            self.cur,
            """SELECT c.id, c.name, c.role,
                      MAX(CASE WHEN i.kind = 'email' THEN i.pii_ref_id::text END) AS email_ref,
                      MAX(CASE WHEN i.kind = 'phone' THEN i.pii_ref_id::text END) AS phone_ref
               FROM contacts.company_contacts c
               LEFT JOIN contacts.contact_identities i ON i.contact_id = c.id
               WHERE c.org_id = current_setting('app.tenant_id', true)::uuid
                 AND c.company_id = %s
               GROUP BY c.id, c.name, c.role""",
            (company_id,),
        )


# ==========================================================================
class IntelligenceRepo:
    def __init__(self, cur: psycopg.Cursor):
        self.cur = cur

    def add_raw_result(self, job_id: str, provider_id: str, query: str, url: str,
                       title: str | None, snippet: str | None) -> bool:
        row = _one(
            self.cur,
            """INSERT INTO intelligence.raw_discovery_results
                 (org_id, job_id, provider_id, query, url, title, snippet)
               VALUES (current_setting('app.tenant_id', true)::uuid, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (org_id, job_id, url) DO NOTHING
               RETURNING id""",
            (job_id, provider_id, query, url, title, snippet),
        )
        return row is not None

    def mark_visited(self, job_id: str, url: str) -> bool:
        import hashlib
        url_hash = hashlib.sha256(url.encode()).hexdigest()
        row = _one(
            self.cur,
            """INSERT INTO intelligence.visited_sources (org_id, job_id, url, url_hash)
               VALUES (current_setting('app.tenant_id', true)::uuid, %s, %s, %s)
               ON CONFLICT (org_id, url_hash) DO NOTHING RETURNING id""",
            (job_id, url, url_hash),
        )
        return row is not None

    def record_enrichment(self, company_id: str, provider_id: str, operation: str,
                          status: str, failure_class: str | None = None,
                          cost_cents: float = 0, effect_id: str | None = None) -> None:
        self.cur.execute(
            """INSERT INTO intelligence.enrichment_attempts
                 (org_id, company_id, provider_id, operation, status, failure_class,
                  cost_cents, effect_id)
               VALUES (current_setting('app.tenant_id', true)::uuid, %s, %s, %s, %s, %s, %s, %s)""",
            (company_id, provider_id, operation, status, failure_class, cost_cents, effect_id),
        )

    def cache_verification(self, cache_key: str, status: str, evidence: dict[str, Any],
                           expires_at: datetime) -> None:
        self.cur.execute(
            """INSERT INTO intelligence.verification_cache
                 (org_id, cache_key, status, evidence, expires_at)
               VALUES (current_setting('app.tenant_id', true)::uuid, %s, %s, %s, %s)
               ON CONFLICT (org_id, cache_key) DO UPDATE
                 SET status = EXCLUDED.status, evidence = EXCLUDED.evidence,
                     expires_at = EXCLUDED.expires_at""",
            (cache_key, status, psycopg.types.json.Json(evidence), expires_at),
        )

    def get_cached_verification(self, cache_key: str) -> dict[str, Any] | None:
        return _one(
            self.cur,
            """SELECT status, evidence FROM intelligence.verification_cache
               WHERE org_id = current_setting('app.tenant_id', true)::uuid
                 AND cache_key = %s AND expires_at > now()""",
            (cache_key,),
        )

    def record_verification(self, contact_id: str, kind: str, pii_ref_id: str | None,
                            status: str, provider_id: str, evidence: dict[str, Any]) -> None:
        self.cur.execute(
            """INSERT INTO intelligence.verification_records
                 (org_id, contact_id, kind, pii_ref_id, status, provider_id, evidence)
               VALUES (current_setting('app.tenant_id', true)::uuid, %s, %s, %s, %s, %s, %s)""",
            (contact_id, kind, pii_ref_id, status, provider_id,
             psycopg.types.json.Json(evidence)),
        )

    def add_scoring_record(self, company_id: str, score: float, score_version: str,
                           input_snapshot: dict[str, Any], explanations: list[str]) -> None:
        self.cur.execute(
            """INSERT INTO intelligence.scoring_records
                 (org_id, company_id, score, score_version, input_snapshot, explanations)
               VALUES (current_setting('app.tenant_id', true)::uuid, %s, %s, %s, %s, %s)""",
            (company_id, score, score_version,
             psycopg.types.json.Json(input_snapshot), psycopg.types.json.Json(explanations)),
        )

    def add_qualification_record(self, company_id: str, campaign_id: str | None,
                                 decision: str, reasons: list[str],
                                 icp_version_id: str | None, policy_version: str) -> None:
        self.cur.execute(
            """INSERT INTO intelligence.qualification_records
                 (org_id, company_id, campaign_id, decision, reasons, icp_version_id,
                  policy_version)
               VALUES (current_setting('app.tenant_id', true)::uuid, %s, %s, %s, %s, %s, %s)""",
            (company_id, campaign_id, decision, psycopg.types.json.Json(reasons),
             icp_version_id, policy_version),
        )

    def add_intent_signal(self, company_id: str, kind: str, signal: str,
                          source_id: str | None = None) -> None:
        self.cur.execute(
            """INSERT INTO intelligence.intent_signals
                 (org_id, company_id, kind, signal, source_id)
               VALUES (current_setting('app.tenant_id', true)::uuid, %s, %s, %s, %s)""",
            (company_id, kind, signal, source_id),
        )

    def company_context(self, company_id: str) -> dict[str, Any]:
        row = _one(
            self.cur,
            """SELECT * FROM company_identity.companies
               WHERE org_id = current_setting('app.tenant_id', true)::uuid AND id = %s""",
            (company_id,),
        )
        intents = _q(
            self.cur,
            """SELECT count(*) AS n FROM intelligence.intent_signals
               WHERE org_id = current_setting('app.tenant_id', true)::uuid AND company_id = %s""",
            (company_id,),
        )
        return {**row, "_intent_count": intents[0]["n"]} if row else {}

    def latest_score(self, company_id: str) -> float:
        row = _one(
            self.cur,
            """SELECT score FROM intelligence.scoring_records
               WHERE org_id = current_setting('app.tenant_id', true)::uuid
                 AND company_id = %s
               ORDER BY created_at DESC LIMIT 1""",
            (company_id,),
        )
        return float(row["score"]) if row else 0.0
