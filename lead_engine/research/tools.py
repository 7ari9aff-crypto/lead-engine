"""Scoped research tools — the ONLY actions the agent can take.

Rules enforced here (directive §31-32):
- Tool capability ≠ permission: every tool declares scopes, and execution
  checks them at call time against the agent's tool_policy — declaring a tool
  in the prompt is never enough.
- Human decisions (APPROVE_CONTACT / REJECT / RESEARCH_MORE / SAVE_FOR_LATER)
  are NOT tools: they do not exist in this registry, so no prompt or model
  output can invoke them.
- There is deliberately NO send/outreach tool of any kind.
- Every call records an agent_step and bumps the job budget counters.
"""
import json
from dataclasses import dataclass, field
from typing import Callable

from ..agent_registry import AgentRegistry
from ..pipeline.normalize import clean_title, domain_from_url, extract_contacts, is_social
from ..providers.email import VerificationPipeline
from ..truth import FactsStore
from .qualification import QualificationError, qualify_from_facts


class ScopeDenied(PermissionError):
    pass


class ToolNotFound(LookupError):
    pass


@dataclass
class ToolContext:
    db: object
    router: object
    store: FactsStore
    manager: object                 # ResearchJobManager
    job_id: str
    allowed_scopes: set = field(default_factory=set)
    run_id: str | None = None


@dataclass
class ToolSpec:
    name: str
    description: str
    scopes: tuple
    handler: Callable


def _slug(name: str) -> str:
    import re
    slug = re.sub(r"[^a-z0-9\u0600-\u06FF]+", "-", (name or "").strip().lower()).strip("-")
    return slug[:60] or "unknown"


def canonical_subject(args: dict) -> tuple[str, str]:
    """Stable subject identity: domain when known, else a slug of the name —
    so 'Clinic A' from two searches collapses to one subject."""
    domain = (args.get("domain") or "").strip().lower().removeprefix("http://") \
        .removeprefix("https://").removeprefix("www.")
    domain = domain.split("/")[0]
    if domain:
        return "company", domain
    name = args.get("name") or ""
    return "company", f"name:{_slug(name)}"


# ------------------------------------------------------------------ handlers
def _tool_search(ctx: ToolContext, args: dict) -> dict:
    query = (args.get("query") or "").strip()
    if not query:
        return {"error": "query مطلوب"}
    max_results = int(args.get("max_results") or 8)
    result, meta = ctx.router.route(
        "web_search", {"query": query, "max_results": max_results},
        job_id=ctx.job_id, cache_data_type="search_results")
    ctx.manager.bump_counter(ctx.job_id, "searches")
    city = args.get("city")
    country = args.get("country") or "SA"
    candidates = []
    auto_saved = 0
    for r in result.get("results", []):
        domain = domain_from_url(r.get("url", ""))
        social = is_social(domain)
        name = clean_title(r.get("title", ""))
        candidates.append({
            "name": name, "domain": None if social else domain,
            "url": r.get("url"), "snippet": r.get("snippet", ""),
            "city": city, "provider": meta.get("provider"),
        })
        # deterministic collection (stage 1 depth): every snippet already
        # carries evidence-backed contacts — extract and persist them with
        # their source URL, so filtering/presentation never depends on the
        # model remembering to save. Same provenance rules as save_fact.
        blob = f"{name} {r.get('snippet', '')}"
        phones, email = extract_contacts(blob, country)
        subject_kind, subject_id = canonical_subject({"name": name, "domain": domain})
        if social:
            ctx.store.add_visit(ctx.job_id, r.get("url"), title=name,
                                summary="social profile discovered")
            continue
        try:
            if name:
                ctx.store.record_fact(subject_kind, subject_id, "name", name,
                                      source_url=r.get("url"), provider=meta.get("provider"),
                                      query=query, job_id=ctx.job_id, run_id=ctx.run_id)
                auto_saved += 1
            if phones:
                ctx.store.record_fact(subject_kind, subject_id, "phone", phones[0],
                                      source_url=r.get("url"), provider=meta.get("provider"),
                                      query=query, quote=r.get("snippet", "")[:200],
                                      job_id=ctx.job_id, run_id=ctx.run_id)
                auto_saved += 1
            if email:
                ctx.store.record_fact(subject_kind, subject_id, "email", email,
                                      source_url=r.get("url"), provider=meta.get("provider"),
                                      query=query, quote=r.get("snippet", "")[:200],
                                      job_id=ctx.job_id, run_id=ctx.run_id)
                auto_saved += 1
            if city:
                ctx.store.record_fact(subject_kind, subject_id, "city", city,
                                      source_url=r.get("url"), provider=meta.get("provider"),
                                      query=query, job_id=ctx.job_id, run_id=ctx.run_id)
                auto_saved += 1
        except Exception as exc:  # one bad result never kills the search round
            candidates[-1]["autosave_error"] = f"{type(exc).__name__}: {exc}"
    row = ctx.db.one(
        "SELECT COUNT(DISTINCT subject_id) AS n FROM research_facts"
        " WHERE job_id=? AND subject_kind='company'", (ctx.job_id,))
    ctx.manager.set_counter(ctx.job_id, "candidates", row["n"] if row else 0)
    return {"provider": meta.get("provider"), "count": len(candidates),
            "auto_saved_facts": auto_saved, "candidates": candidates}


def _tool_research_company(ctx: ToolContext, args: dict) -> dict:
    """Deep-dive one company through the OpenManus browsing runtime (R4).
    Honest degradation: when the runtime is not configured the tool says so —
    it never fabricates research."""
    from . import openmanus
    subject_kind, subject_id = canonical_subject(args)
    if not openmanus.is_configured():
        return {"status": "UNAVAILABLE",
                "note": "OpenManus runtime غير مهيأ (OPENMANUS_BASE_URL) — "
                        "الاكتفاء بمقتطفات البحث، ولا اختراع معلومات"}
    objective = args.get("objective") or f"Investigate {subject_id}"
    result = openmanus.research_company(ctx.router, ctx.db, subject_id, objective,
                                        job_id=ctx.job_id)
    ctx.manager.bump_counter(ctx.job_id, "browse_calls")
    if result.get("facts"):
        for f in result["facts"]:
            ctx.store.record_fact(
                subject_kind, subject_id, f.get("field", "note"), f.get("value", ""),
                source_url=f.get("source_url"), source_kind="openmanus",
                provider="openmanus", quote=f.get("quote"), job_id=ctx.job_id,
                run_id=ctx.run_id, inferred=f.get("inferred", False))
    ctx.store.add_visit(ctx.job_id, result.get("url") or f"openmanus://{subject_id}",
                        title=result.get("title"), http_status=result.get("http_status"),
                        summary=result.get("summary"))
    return result


def _tool_save_fact(ctx: ToolContext, args: dict) -> dict:
    subject_kind, subject_id = canonical_subject(args)
    field = (args.get("field") or "").strip()
    value = args.get("value")
    if not field or value in (None, ""):
        return {"error": "field و value مطلوبان"}
    fact = ctx.store.record_fact(
        subject_kind, subject_id, field, value,
        source_url=args.get("source_url"), source_kind=args.get("source_kind") or "search_api",
        provider=args.get("provider"), query=args.get("query"),
        quote=args.get("quote"), job_id=ctx.job_id, run_id=ctx.run_id,
        inferred=bool(args.get("inferred")))
    if field in ("domain", "name", "city", "country", "email", "phone"):
        row = ctx.db.one(
            "SELECT COUNT(DISTINCT subject_id) AS n FROM research_facts"
            " WHERE job_id=? AND subject_kind='company'", (ctx.job_id,))
        ctx.manager.set_counter(ctx.job_id, "candidates", row["n"] if row else 0)
    return {"saved": True, "fact_id": fact["fact_id"], "status": fact["status"],
            "subject": subject_id}


def _tool_verify_fact(ctx: ToolContext, args: dict) -> dict:
    fact_id = args.get("fact_id")
    fact = ctx.store.get_fact(fact_id) if fact_id else None
    if not fact:
        return {"error": "fact_id غير موجود"}
    if fact["field"] == "email":
        verdict = VerificationPipeline(ctx.router).verify(fact["value"])
        outcome = "verified" if verdict.get("status") == "DELIVERABLE" else "refuted"
        updated = ctx.store.verify_fact(
            fact_id, outcome=outcome, confidence=verdict.get("confidence"),
            provider=verdict.get("via"), quote=json.dumps(
                {"status": verdict.get("status"), "reason":
                    (verdict.get("details") or {}).get("reason")}, ensure_ascii=False))
        ctx.manager.bump_counter(ctx.job_id, "verifications")
        return {"fact_id": fact_id, "outcome": outcome,
                "email_status": verdict.get("status"), "status": updated["status"]}
    return {"error": "التحقق الآلي متاح حاليًا لحقول الإيميل فقط — للحقل الواحد "
                     "أضف مصدرًا ثانيًا مستقلًا ليتحقق تلقائيًا"}


def _tool_list_facts(ctx: ToolContext, args: dict) -> dict:
    subject_kind, subject_id = canonical_subject(args)
    return ctx.store.snapshot(subject_kind, subject_id)


def _tool_qualify(ctx: ToolContext, args: dict) -> dict:
    subject_kind, subject_id = canonical_subject(args)
    icp = args.get("icp") or _active_icp(ctx)
    try:
        verdict = qualify_from_facts(ctx.db, ctx.router, subject_kind, subject_id,
                                     icp, store=ctx.store, job_id=ctx.job_id)
    except QualificationError as exc:
        return {"error": str(exc)}
    ctx.manager.bump_counter(ctx.job_id, "qualifications")
    return verdict


def _active_icp(ctx: ToolContext) -> dict:
    from ..icp_store import ICPStore

    icps = ICPStore(ctx.db)
    ctx_row = ctx.manager.context(ctx.job_id) or {}
    if ctx_row.get("icp_version_id"):
        row = icps.get(ctx_row["icp_version_id"])
        if row:
            return row["definition"]
    row = icps.active("agentic")
    if row:
        return row["definition"]
    return {"industry": "general", "cities": [], "keywords_en": [],
            "keywords_ar": [], "criteria": {}}


def _tool_status(ctx: ToolContext, args: dict) -> dict:
    return ctx.manager.progress(ctx.job_id)


def _tool_ask_user(ctx: ToolContext, args: dict) -> dict:
    question = (args.get("question") or "").strip()
    if not question:
        return {"error": "question مطلوب"}
    qid = ctx.store.add_open_question(ctx.job_id, question,
                                      subject_id=args.get("subject_id"))
    ctx.manager.waiting_for_user(ctx.job_id, question)
    return {"status": "WAITING_FOR_USER", "question_id": qid, "question": question}


# ------------------------------------------------------------------ registry
TOOLS: dict[str, ToolSpec] = {
    spec.name: spec for spec in (
        ToolSpec("search_companies",
                 "ابحث في الويب عن شركات/عملاء محتملين باستعلام محدد ويعيد مرشحين",
                 ("search:read",), _tool_search),
        ToolSpec("research_company",
                 "تحقيق عميق في شركة واحدة عبر تصفح مصادرها (OpenManus) وإضافة الحقائق",
                 ("research:read", "evidence:write"), _tool_research_company),
        ToolSpec("save_fact",
                 "احفظ ملاحظة موثقة عن شركة (حقل/قيمة/مصدر) في طبقة الحقيقة",
                 ("evidence:write",), _tool_save_fact),
        ToolSpec("verify_fact",
                 "تحقق من حقيقة مخزنة (الإيميل بالفحص 5-حالات)",
                 ("verification:run",), _tool_verify_fact),
        ToolSpec("list_facts",
                 "اعرض الحقائق المخزنة عن شركة بحالتها ومصادرها",
                 ("facts:read",), _tool_list_facts),
        ToolSpec("qualify_lead",
                 "قيّم الشركة مقابل الـICP من الحقائق المخزنة فقط (بدون بحث جديد)",
                 ("qualification:run",), _tool_qualify),
        ToolSpec("get_research_status",
                 "حالة مهمة البحث الحالية: العدادات، الموازين، التعارضات",
                 ("jobs:read",), _tool_status),
        ToolSpec("ask_user",
                 "اسأل المستخدم سؤالًا يمنع التقدم — المهمة تنتظر إجابته",
                 ("interaction:write",), _tool_ask_user),
    )
}

DECLARATIONS = [{"name": s.name, "description": s.description,
                 "parameters": {"type": "OBJECT", "properties": {}}}
                for s in TOOLS.values()]

# The actor prompt MUST enumerate the exact tool names + argument shapes —
# a live model that has to guess names calls "search"/"web_search" and every
# action dies with "أداة غير موجودة" (caught by the real smoke test).
TOOLS_DOC = """الأدوات المتاحة (استخدم الأسماء حرفيًا كما هي):

1. search_companies — ابحث في الويب عن شركات/عملاء
   args: {"query": "نص البحث", "city": "المدينة", "max_results": 8}
2. save_fact — احفظ ملاحظة موثقة عن شركة في طبقة الحقيقة (كل معلومة تتعلمها تُحفظ فورًا)
   args: {"name": "اسم الشركة", "domain": "النطاق إن وجد", "field": "phone|email|city|branches|employee_count|decision_maker|...",
          "value": "القيمة", "source_url": "رابط المصدر", "provider": "tavily|brave|exa|openmanus",
          "quote": "الجملة الدالة", "inferred": false}
   (لو الحقيقة استنتاج بلا مصدر مباشر: inferred=true واكتب السبب في quote)
3. verify_fact — تحقق من حقيقة محفوظة (للإيميل: فحص 5-حالات)
   args: {"fact_id": "معرف الحقيقة"}
4. list_facts — اعرض حقائق شركة
   args: {"domain": "..."} أو {"name": "..."}
5. qualify_lead — قيّم شركة مقابل الـICP من الحقائق المخزنة فقط
   args: {"domain": "..."} أو {"name": "..."}
6. get_research_status — حالة المهمة (بدون args)
7. ask_user — اسأل المستخدم سؤالًا يحجب التقدم
   args: {"question": "السؤال"}
8. research_company — تحقيق عميق عبر تصفح OpenManus (لو غير مهيأ سيُقال لك)
   args: {"domain": "...", "objective": "ما تبحث عنه"}

ملاحظة صارمة: القيم اللي تتعلمها من مقتطفات البحث تُحفظ بـsave_fact مع
source_url — ممنوع تعتمد على ذاكرتك بين الجولات."""


def render_tool_docs() -> str:
    return TOOLS_DOC


def execute_tool(ctx: ToolContext, name: str, args: dict,
                 *, registry: AgentRegistry | None = None) -> dict:
    """One scoped, budgeted, audited tool execution."""
    spec = TOOLS.get(name)
    if spec is None:
        return {"error": f"أداة غير موجودة: {name}"}
    missing = [s for s in spec.scopes if s not in ctx.allowed_scopes]
    if missing:
        raise ScopeDenied(f"{name} يحتاج صلاحيات {missing} غير ممنوحة لهذا الوكيل")
    ok, exceeded, _snap = ctx.manager.budget_check(ctx.job_id)
    if not ok:
        return {"error": f"budget exceeded: {exceeded}",
                "budget_stop": exceeded}
    step_id = registry.start_step(ctx.run_id, f"tool:{name}",
                                  input_data=args) if registry and ctx.run_id else None
    try:
        out = spec.handler(ctx, args or {})
        if step_id:
            registry.finish_step(step_id, "COMPLETED",
                                 output={"summary": json.dumps(out, ensure_ascii=False,
                                                                default=str)[:400]})
    except Exception as exc:
        if step_id:
            registry.finish_step(step_id, "FAILED", error=f"{type(exc).__name__}: {exc}")
        raise
    ctx.manager.bump_counter(ctx.job_id, "tool_calls")
    return out
