"""Stage 3 — Presentation layer: the interpretation payload per lead.

This is NOT a leads screen; it is an interpretation layer (directive §26).
For every lead the user sees:

- identity (company facts with their statuses)
- fit: qualification verdict + rationale ("why") + confidence
- verification: 5-state email statuses, verified-fact count
- conflicts: open value conflicts, never silently resolved
- missing information: what the research could NOT establish
- freshness: which facts are STALE
- sources: the full provenance trail

And the four HUMAN decisions (§27) — APPROVE_CONTACT / REJECT /
RESEARCH_MORE / SAVE_FOR_LATER — are recorded here and nowhere else. Even at
fit_score = 100 there is no automatic outbound (§27).
"""
import json

from ..truth import STATUS_CONFLICTED, STATUS_STALE, FactsStore


def _lead_identity(lead: dict, snapshot: dict) -> dict:
    fields = snapshot["fields"]
    def pick(field):
        node = fields.get(field)
        if not node:
            return None
        return {"value": node["value"], "status": node["status"],
                "confidence": node["confidence"]}
    return {
        "name": pick("name") or {"value": lead.get("name"), "status": "UNVERIFIED",
                                 "confidence": 0.4},
        "domain": pick("domain") or ({"value": lead.get("domain"),
                                      "status": "UNVERIFIED",
                                      "confidence": 0.5} if lead.get("domain") else None),
        "city": pick("city"),
        "country": pick("country"),
        "industry": pick("industry"),
        "employee_count": pick("employee_count"),
        "branches": pick("branches"),
    }


def stored_verdict(lead: dict) -> dict | None:
    """The qualification verdict captured at research time (raw.pipeline.qualification)."""
    raw = lead.get("raw")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None
    if not isinstance(raw, dict):
        return None
    return (raw.get("pipeline") or {}).get("qualification")


def missing_information(snapshot: dict, verdict: dict | None) -> list[str]:
    """Fields the research could NOT establish, or that the qualifier flagged."""
    missing = set(verdict.get("unknown_fields") or []) if verdict else set()
    for field, node in snapshot["fields"].items():
        if node["status"] in (STATUS_CONFLICTED, STATUS_STALE):
            missing.add(field)
    return sorted(missing)


def build_presentation(db, lead: dict, *, store: FactsStore | None = None,
                       subject_id: str | None = None) -> dict:
    from .tools import canonical_subject

    store = store or FactsStore(db)
    if not subject_id:
        kind, subject_id = canonical_subject({
            "name": lead.get("name"), "domain": lead.get("domain")})
    else:
        kind = "company"
    snapshot = store.snapshot(kind, subject_id)
    verdict = stored_verdict(lead)

    contact_fields = ("email", "phone", "decision_maker", "linkedin")
    verification = {
        "email_status": lead.get("email_status"),
        "email_confidence": lead.get("email_confidence"),
        "verified_facts": sum(
            1 for n in snapshot["fields"].values() if n["status"] == "VERIFIED"),
        "contact_coverage": {
            f: bool(snapshot["fields"].get(f) or lead.get(f))
            for f in contact_fields
        },
    }
    return {
        "lead": {
            "lead_id": lead.get("lead_id"),
            "job_id": lead.get("job_id"),
            "stage": lead.get("stage"),
            "score": lead.get("score"),
            "qualification_score": lead.get("qualification_score"),
            "tier": lead.get("tier"),
            "disposition": lead.get("disposition"),
            "disposition_note": lead.get("disposition_note"),
            "disposition_at": lead.get("disposition_at"),
        },
        "subject": {"kind": kind, "id": subject_id},
        "identity": _lead_identity(lead, snapshot),
        "fit": {
            "fit_score": (verdict or {}).get("fit_score", lead.get("qualification_score")),
            "tier": (verdict or {}).get("tier", lead.get("tier")),
            "why": (verdict or {}).get("why", []),
            "confidence": (verdict or {}).get("confidence"),
            "blockers": (verdict or {}).get("blockers", []),
            "processing_mode": (verdict or {}).get("processing_mode"),
            "deterministic": (verdict or {}).get("deterministic", False),
        },
        "verification": verification,
        "facts_snapshot": snapshot,
        "missing_information": missing_information(snapshot, verdict),
        "conflicts": snapshot["conflicts"],
        "stale_fields": snapshot["stale_fields"],
        "sources_count": sum(len(n["sources"]) for n in snapshot["fields"].values()),
    }
