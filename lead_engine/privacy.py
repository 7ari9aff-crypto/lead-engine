"""PII retention sweep + erasure (register DATA-03).

`legal_gate` computes a per-lead retention horizon; the pipeline persists it
inside the lead's `raw` JSON under "pipeline" (there is no dedicated column —
adding one would require a production migration and insert-column sync on both
backends before any deploy, so the sweep reads it from raw instead). Nothing
enforced it until now: contact PII lived on the row indefinitely.

Erasure semantics, fixed by measurement:
  * `raw` is redacted along with the PII columns — insert_lead serialises every
    non-column key into raw, so column-only erasure would be fake erasure.
  * The marker is `legal_decision = 'retention-erased'`, NOT `disposition`
    (disposition is documented human-only). The erasure reason is APPENDED to
    disposition_note so an existing human decision record survives.
  * Aggregates survive: stage, scores, domain, name, sources — the compliance
    duty is to forget people, not to falsify history.

Both entry points share `_anonymize` so the sweep and a data-subject request
cannot drift. On Postgres every query flows through the per-request org GUC
(db_pg._bind_org), so the sweep only ever touches the caller's tenant.
"""
import json
from datetime import datetime, timedelta, timezone

_DEFAULT_RETENTION_DAYS = 30  # mirrors legal_gate's policy default

ANON_COLUMNS = ("email", "phone", "decision_maker", "decision_maker_title",
                "linkedin", "social")

_MARK = "retention-erased"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_ts(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _retention_days(row) -> int:
    try:
        raw = row.get("raw")
        payload = raw if isinstance(raw, dict) else json.loads(raw or "{}")
        days = (payload.get("pipeline") or {}).get("retention_days")
        return int(days)
    except (TypeError, ValueError):
        return _DEFAULT_RETENTION_DAYS


def _redacted_raw() -> str:
    return json.dumps({"retention": "erased", "erased_at": _now_iso()},
                      ensure_ascii=False)


def _anonymize(db, lead_ids: list[str], reason: str) -> int:
    if not lead_ids:
        return 0
    now = _now_iso()
    placeholders = ", ".join("?" for _ in lead_ids)
    set_cols = ", ".join(f"{c} = NULL" for c in ANON_COLUMNS)
    db.execute(
        f"UPDATE leads SET {set_cols},"
        " raw = ?,"
        f" legal_decision = '{_MARK}',"
        " disposition_note = CASE"
        "   WHEN disposition_note IS NULL OR disposition_note = '' THEN ?"
        "   ELSE disposition_note || ' | ' || ? END,"
        " disposition_at = ?, updated_at = ?"
        f" WHERE lead_id IN ({placeholders})"
        f"   AND (legal_decision IS NULL OR legal_decision <> '{_MARK}')",
        (_redacted_raw(), reason, reason, now, now, *lead_ids),
    )
    return len(lead_ids)


def retain_expired(db, now: datetime | None = None) -> int:
    """Anonymize every lead whose retention window has elapsed. Returns the
    number of rows anonymized. Cheap by construction: one SELECT of candidate
    rows, date math in Python, one UPDATE (a generated retention_expiry_ts
    column is the follow-up at 10k+ rows — see gap register)."""
    now = now or datetime.now(timezone.utc)
    rows = db.query(
        "SELECT lead_id, created_at, raw FROM leads"
        f" WHERE legal_decision IS NULL OR legal_decision <> '{_MARK}'"
    )
    expired: list[str] = []
    for row in rows:
        created = _parse_ts(row.get("created_at"))
        if created is None:
            continue
        if created + timedelta(days=_retention_days(row)) < now:
            expired.append(row["lead_id"])
    return _anonymize(db, expired, "retention window elapsed")


def erase_lead(db, lead_id: str, actor: str) -> bool:
    """Erase one lead on request (data-subject erasure), regardless of its
    retention window, and record who ordered it in the audit trail."""
    row = db.one("SELECT lead_id FROM leads WHERE lead_id = ?", (lead_id,))
    if row is None:
        return False
    _anonymize(db, [lead_id], f"erased-by-request by {actor}")
    db.audit(actor, "privacy.erase", "lead", lead_id,
             {"legal_decision": _MARK})
    return True
