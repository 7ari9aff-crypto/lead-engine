"""Direct lead push to HubSpot (CSV export was the only path before).

Design rules, all enforced here and covered by tests/test_crm_push.py:

* Only leads that already passed the product's own gates are pushed:
  stage ACCEPTED, storage not rejected by the legal gate, no INVALID email,
  and the contact is not on the org's do-not-contact list.
* Idempotent. HubSpot "batch upsert" is keyed on email, so re-pushing the
  same lead updates the contact instead of creating a duplicate. Leads with
  no email are skipped (HubSpot cannot upsert without an id property).
* Dry run is the default. Nothing leaves the system unless the caller
  explicitly passes dry_run=False.
* The HTTP layer is injected (``http_post``), so the logic is testable with
  no network, and the real call goes only to the fixed HubSpot host.
* Tokens come from integrations.get_valid_access_token (encrypted at rest,
  refreshed under a lock). They are never logged or returned.
"""
from __future__ import annotations

import re
from typing import Callable, Iterable

HUBSPOT_BASE = "https://api.hubapi.com"
UPSERT_PATH = "/crm/v3/objects/contacts/batch/upsert"
BATCH_SIZE = 100  # HubSpot batch limit

PUSHABLE_STAGE = "ACCEPTED"
ERASED_MARK = "retention-erased"  # lead_engine/privacy.py

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Reason codes (stable strings: shown to the operator and asserted in tests)
SKIP_STAGE = "stage_not_accepted"
SKIP_LEGAL = "legal_gate_rejected"
SKIP_ERASED = "retention_erased"
SKIP_REVIEWER_REJECTED = "reviewer_rejected"
SKIP_NO_EMAIL = "no_email"
SKIP_BAD_EMAIL = "invalid_email"
SKIP_EMAIL_STATUS = "email_verified_invalid"
SKIP_SUPPRESSED = "suppressed"
SKIP_DUPLICATE = "duplicate_in_batch"


def _split_name(full: str | None) -> tuple[str, str]:
    parts = (full or "").strip().split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def eligibility(lead: dict, is_suppressed: Callable[[str], tuple[bool, str | None]]
                ) -> str | None:
    """Return a skip-reason code, or None when the lead may be pushed."""
    # Erased data must never leave the system again (privacy.py marks erased
    # rows with legal_decision = 'retention-erased'). Checked first.
    if lead.get("legal_decision") == ERASED_MARK:
        return SKIP_ERASED
    if (lead.get("disposition") or "").upper() == "REJECT":
        return SKIP_REVIEWER_REJECTED
    if (lead.get("stage") or "").upper() != PUSHABLE_STAGE:
        return SKIP_STAGE
    if lead.get("legal_decision") == "REJECTED":
        return SKIP_LEGAL
    email = (lead.get("email") or "").strip().lower()
    if not email:
        return SKIP_NO_EMAIL
    if not _EMAIL_RE.match(email):
        return SKIP_BAD_EMAIL
    if (lead.get("email_status") or "").upper() == "INVALID":
        return SKIP_EMAIL_STATUS
    suppressed, _ = is_suppressed(email)
    if suppressed:
        return SKIP_SUPPRESSED
    return None


def to_hubspot_contact(lead: dict) -> dict:
    """Map a lead row to a HubSpot upsert input (id = email)."""
    email = lead["email"].strip().lower()
    # Prefer the decision maker's name for a *contact*; fall back to company.
    first, last = _split_name(lead.get("decision_maker"))
    props = {
        "email": email,
        "firstname": first,
        "lastname": last,
        "jobtitle": lead.get("decision_maker_title") or "",
        "company": lead.get("name") or "",
        "phone": lead.get("phone") or "",
        "website": lead.get("website") or (f"https://{lead['domain']}"
                                           if lead.get("domain") else ""),
        "city": lead.get("city") or "",
        "country": lead.get("country") or "",
        "industry": lead.get("industry") or "",
        "hs_linkedin_url": lead.get("linkedin") or "",
    }
    # HubSpot rejects empty-string numeric/enum props on some portals and an
    # empty value would also overwrite good data on update, so omit blanks.
    props = {k: v for k, v in props.items() if v not in ("", None)}
    return {"id": email, "idProperty": "email", "properties": props}


def plan(leads: Iterable[dict], is_suppressed: Callable[[str], tuple[bool, str | None]]
         ) -> dict:
    """Decide what would be pushed. Pure function, no side effects."""
    inputs: list[dict] = []
    skipped: list[dict] = []
    seen: set[str] = set()
    for lead in leads:
        reason = eligibility(lead, is_suppressed)
        if reason is None:
            email = lead["email"].strip().lower()
            if email in seen:
                reason = SKIP_DUPLICATE
            else:
                seen.add(email)
        if reason:
            skipped.append({"lead_id": lead.get("lead_id"), "reason": reason})
            continue
        inputs.append(to_hubspot_contact(lead))
    return {"inputs": inputs, "skipped": skipped}


def _chunks(items: list, n: int):
    for i in range(0, len(items), n):
        yield items[i:i + n]


def push(leads: Iterable[dict], *, is_suppressed, access_token: Callable[[], str],
         http_post: Callable[..., object], dry_run: bool = True) -> dict:
    """Plan and (unless dry_run) send to HubSpot. Never raises on a bad batch:
    failures are reported per batch so one error cannot hide the others."""
    p = plan(leads, is_suppressed)
    summary = {
        "dry_run": dry_run,
        "eligible": len(p["inputs"]),
        "skipped": len(p["skipped"]),
        "skipped_detail": p["skipped"],
        "pushed": 0,
        "failed_batches": [],
    }
    skipped_by_reason: dict[str, int] = {}
    for s in p["skipped"]:
        skipped_by_reason[s["reason"]] = skipped_by_reason.get(s["reason"], 0) + 1
    summary["skipped_by_reason"] = skipped_by_reason
    if dry_run or not p["inputs"]:
        return summary

    token = access_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    for idx, batch in enumerate(_chunks(p["inputs"], BATCH_SIZE)):
        try:
            resp = http_post(HUBSPOT_BASE + UPSERT_PATH, json={"inputs": batch},
                             headers=headers, timeout=30)
            code = getattr(resp, "status_code", 0)
            if 200 <= code < 300:
                summary["pushed"] += len(batch)
            else:
                # status + short body only: never echo request data or token
                summary["failed_batches"].append(
                    {"batch": idx, "size": len(batch), "status": code,
                     "error": (getattr(resp, "text", "") or "")[:200]})
        except Exception as exc:  # network error: record, keep going
            summary["failed_batches"].append(
                {"batch": idx, "size": len(batch), "status": None,
                 "error": type(exc).__name__})
    return summary
