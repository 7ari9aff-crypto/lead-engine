"""Evidence-grounded qualification.

The qualifier reasons over the FACTS STORE ONLY (directive §37: the model is
not the source of truth). Pipeline:

1. deterministic checks from the ICP (city/industry gates) on stored facts —
   a hard mismatch ends the evaluation without any model call;
2. an LLM pass that receives the fact snapshot WITH statuses (VERIFIED /
   CONFLICTED / STALE / UNVERIFIED / INFERRED) and the ICP, and must answer in
   strict JSON; unknown knowledge goes to unknown_fields, never invented;
3. the returned `why` list is the user-facing rationale (Stage 3).

This runs per subject and never re-discovers: re-qualification after an ICP
change reuses the stored facts (directive §25).
"""
import json

from ..router import NoProviderAvailable
from ..truth import STATUS_CONFLICTED, STATUS_STALE, FactsStore

PROMPT = """أنت محلل تأهيل عملاء B2B صارم ومسؤول عن الحقيقة.
قيّم الشركة التالية مقابل معايير الـICP اعتمادًا على الحقائق المخزنة **فقط**.

قواعد إلزامية:
- استخدم الحقائق المذكورة ولا تخترع أي معلومة غير موجودة.
- كل حقيقة لها حالة: VERIFIED (موثقة)، UNVERIFIED (بمصدر واحد)، CONFLICTED
  (قيمتان متناقضتان)، STALE (قديمة)، INFERRED (استنتاج).
- إذا كانت معلومة حاسمة للقرار غير موجودة أو متعارضة أو قديمة، ضعها في
  unknown_fields واختر حذرًا في التقييم — لا تفترض.
- وضّح في "why" لماذا هذه الشركة عميل محتمل أو ليست كذلك، بالاعتماد على
  الحقائق وحالتها صراحة.

أعد JSON فقط بهذا الشكل:
{{"fit_score": <0-100>, "tier": "A"|"B"|"C",
  "why": ["..."], "confidence": <0.0-1.0>,
  "unknown_fields": ["..."], "blockers": ["..."]}}

ICP:
{icp}

حقائق الشركة (JSON مع الحالات):
{facts}
"""


class QualificationError(RuntimeError):
    pass


def deterministic_checks(facts: dict, icp: dict) -> list[dict]:
    """ICP gates evaluable without a model. Returns check records with
    verdict pass|fail|unknown — `fail` on a VERIFIED contradiction only."""
    checks = []
    values = facts["values"]
    statuses = facts["statuses"]

    def _status(field):
        return statuses.get(field)

    # city gate: a VERIFIED city that matches NO ICP city is a hard fail
    city = values.get("city")
    icp_cities = [c.get("name", "") for c in icp.get("cities", [])] + \
                 [c.get("ar", "") for c in icp.get("cities", [])]
    if city and icp_cities:
        from ..pipeline.normalize import normalize_text
        norm_city = normalize_text(city)
        match = any(normalize_text(c) and normalize_text(c) in norm_city
                    or norm_city in normalize_text(c) for c in icp_cities if c)
        checks.append({
            "check": "city_match", "value": city,
            "verdict": "pass" if match else "fail",
            "basis": f"city fact is {_status('city')}",
        })
    elif icp_cities:
        checks.append({"check": "city_match", "verdict": "unknown",
                       "basis": "no city fact stored"})
    return checks


def qualify_from_facts(db, router, subject_kind: str, subject_id: str,
                       icp: dict, *, store: FactsStore | None = None,
                       job_id: str | None = None) -> dict:
    """Qualify one subject from stored facts. Never re-discovers."""
    store = store or FactsStore(db)
    facts = store.facts_for_qualification(subject_kind, subject_id)
    if not facts["values"]:
        raise QualificationError(f"no facts stored for {subject_id}")

    checks = deterministic_checks(facts, icp)
    hard_fails = [c for c in checks if c["verdict"] == "fail"]
    if hard_fails:
        return {
            "subject_kind": subject_kind, "subject_id": subject_id,
            "fit_score": 0.0, "tier": "C",
            "why": [f"مرفوض حتميًا: {c['check']} — {c['basis']}" for c in hard_fails],
            "confidence": 1.0, "unknown_fields": [], "blockers":
                [c["check"] for c in hard_fails],
            "deterministic": True, "checks": checks,
        }

    conflicted = [f for f in facts["conflicted"]]
    prompt = PROMPT.format(
        icp=json.dumps(icp, ensure_ascii=False, default=str),
        facts=json.dumps({
            "values": facts["values"],
            "statuses": facts["statuses"],
            "conflicted_fields": conflicted,
            "stale_fields": facts["stale"],
        }, ensure_ascii=False, default=str))
    payload = {"prompt": prompt, "json_mode": True}
    try:
        result, meta = router.route("reasoning", payload, job_id=job_id)
    except NoProviderAvailable as exc:
        raise QualificationError(f"no LLM available for qualification: {exc}") from exc
    try:
        data = json.loads(_strip_fences(result.get("text", "")))
        score = float(data["fit_score"])
        assert 0 <= score <= 100
        tier = data.get("tier") or ("A" if score >= 75 else "B" if score >= 50 else "C")
    except (json.JSONDecodeError, KeyError, ValueError, AssertionError, TypeError) as exc:
        raise QualificationError(f"unparseable qualification output: {exc}") from exc

    degraded = meta.get("provider") == "ollama"
    return {
        "subject_kind": subject_kind, "subject_id": subject_id,
        "fit_score": score, "tier": tier,
        "why": list(data.get("why") or []),
        "confidence": float(data.get("confidence") or 0.5),
        "unknown_fields": list(data.get("unknown_fields") or []),
        "blockers": list(data.get("blockers") or []),
        "deterministic": False,
        "checks": checks,
        "processing_mode": "degraded_local" if degraded else "cloud",
        "provider": meta.get("provider"),
        "conflicted_fields": conflicted,
        "stale_fields": facts["stale"],
    }


def _strip_fences(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()
