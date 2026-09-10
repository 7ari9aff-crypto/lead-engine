"""Conversational agent — the chat drives the actual engine.

The model (Gemini via the provider pool, so quota/rotation rules apply) gets
function-calling tools that execute real pipeline operations:
run_lead_generation / get_job_status / list_leads / verify_email / system_status.
The loop runs up to MAX_STEPS tool rounds per user message.
"""
import json

from ..benchmark.metrics import compute_metrics
from ..benchmark.run import run_benchmark
from ..pipeline.icp import build_adhoc_icp
from ..providers.email import VerificationPipeline
from ..router import NoProviderAvailable

MAX_STEPS = 6

SYSTEM_INSTRUCTION = """أنت "مساعد محرك الـLeads" — واجهة محادثة لنظام توليد leads واعٍ بالحصص (quotas).
لديك أدوات تنفّذ عمليات حقيقية على النظام: تشغيل التوليد، متابعة المهام، استعراض الـleads، فحص الإيميلات، وحالة النظام.

قواعد:
- اتكلم بالعربية بأسلوب مباشر ومختصر.
- عندما يطلب المستخدم توليد leads (أي مدينة/مجال)، نادِ الأداة run_lead_generation فورًا — لا تسأل تأكيدًا.
- قدّم النتائج كقائمة مختصرة: الاسم، المدينة، الدومين، الرقم، الإيميل، الدرجة.
- كن صادقًا تمامًا حول مصادر البيانات: الأرقام والإيميلات الحالية مستخرجة من مقتطفات نتائج البحث (بمصدرها) فقط، لأن مفاتيح Apollo/Hunter غير مضبوطة بعد — قل ذلك صراحة عندما تعرض جهات اتصال.
- لا تخترع أرقامًا أو إيميلات أو شركات لم تعِدها الأدوات.
- إذا فشلت أداة أو انتهت الحصص، اشرح السبب الحقيقي وما الحل (مثل: إضافة مفتاح)."""

TOOLS_DECL = [{
    "function_declarations": [
        {
            "name": "run_lead_generation",
            "description": "شغّل خط توليد الـleads بالكامل: بحث حقيقي عن الشركات، إزالة التكرار، فلترة، ثم تأهيل بالذكاء الاصطناعي. يعيد قائمة الـleads مع الأرقام والإيميلات المتاحة حاليًا.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "city": {"type": "STRING",
                             "description": "المدينة السعودية مثل: الرياض، جدة، الدمام"},
                    "industry": {"type": "STRING",
                                 "description": "المجال — الافتراضي dental (عيادات أسنان)",
                                 "enum": ["dental"]},
                    "dry_run": {"type": "BOOLEAN",
                                "description": "تشغيل تجربة على بيانات وهمية — افتراضيًا false (تشغيل حقيقي)"},
                    "approval_id": {"type": "STRING", "description": "معرف الموافقة بعد اعتماد التشغيل الحي"},
                },
                "required": ["city"],
            },
        },
        {
            "name": "get_job_status",
            "description": "حالة مهمة توليد محددة: الحالة، الأحداث، ومقاييس التشغيل.",
            "parameters": {
                "type": "OBJECT",
                "properties": {"job_id": {"type": "STRING"}},
                "required": ["job_id"],
            },
        },
        {
            "name": "list_leads",
            "description": "اعرض الـleads المخزنة (مقبولة/مراجعة/مرفوضة) مع أرقامها وإيميلاتها.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "stage": {"type": "STRING",
                              "description": "ACCEPTED أو REVIEW أو REJECTED — فارغ = الكل"},
                    "job_id": {"type": "STRING", "description": "حصر النتائج بمهمة معينة"},
                    "limit": {"type": "INTEGER", "description": "أقصى عدد — افتراضي 15"},
                },
            },
        },
        {
            "name": "verify_email",
            "description": "فحص إيميل بالـ5 حالات (DELIVERABLE/RISKY/CATCH_ALL/INVALID/UNKNOWN) مع كشف catch-all.",
            "parameters": {
                "type": "OBJECT",
                "properties": {"email": {"type": "STRING"}},
                "required": ["email"],
            },
        },
        {
            "name": "system_status",
            "description": "حالة النظام: المزوّدون المتاحون والمستنفدون، عدد المهام والـleads، الاستهلاك.",
            "parameters": {"type": "OBJECT", "properties": {}},
        },
    ]
}]


def _compact_lead(lead: dict) -> dict:
    return {k: lead.get(k) for k in
            ("name", "city", "domain", "phone", "email", "email_status",
             "tier", "score", "website")}


def execute_tool(name: str, args: dict, router, db) -> dict:
    """Execute one tool call against the real engine. Always returns a
    JSON-serializable dict (honest errors included)."""
    args = args or {}
    try:
        if name == "run_lead_generation":
            if not bool(args.get("dry_run", False)) and hasattr(db, "execute"):
                from ..agent_registry import AgentRegistry
                approval_id = args.get("approval_id")
                approval = AgentRegistry(db).approval(approval_id) if approval_id else None
                if not approval or approval["status"] != "APPROVED":
                    run_id = f"approval-request:{args.get('city', 'unknown')}"
                    requested = AgentRegistry(db).request_approval(run_id, "run_lead_generation", args)
                    return {"status": "approval_required", "approval_id": requested,
                            "message": "التشغيل الحي يحتاج موافقة من لوحة الوكلاء قبل استهلاك الحصص."}
            icp = build_adhoc_icp([args.get("city", "الرياض")],
                                  args.get("industry", "dental"))
            summary, metrics, _outputs = run_benchmark(
                icp, dry_run=bool(args.get("dry_run", False)), write=False)
            leads = summary.get("leads", [])
            return {
                "job_id": summary.get("job_id"),
                "state": summary.get("state"),
                "pause_reason": summary.get("pause_reason"),
                "metrics": {k: metrics.get(k) for k in
                            ("discovery_raw_candidates", "unique_after_dedup",
                             "qualification_scored", "final_leads", "review_leads",
                             "quota_units_total", "total_cost_usd")},
                "accepted_leads": [_compact_lead(l) for l in leads
                                   if l.get("stage") == "ACCEPTED"][:15],
                "review_leads_sample": [_compact_lead(l) for l in leads
                                        if l.get("stage") == "REVIEW"][:8],
                "contacts_note": "الأرقام/الإيميلات مستخرجة من مقتطفات نتائج البحث "
                                 "(بمصدرها) — إكمال جهات الاتصال يتطلب مفاتيح Apollo وHunter.",
            }

        if name == "get_job_status":
            job = db.one("SELECT * FROM jobs WHERE job_id=?", (args.get("job_id", ""),))
            if not job:
                return {"error": "لا توجد مهمة بهذا المعرف"}
            stored = {}
            try:
                stored = json.loads(job.get("params") or "{}")
            except json.JSONDecodeError:
                pass
            return {"job_id": job["job_id"], "icp": job["icp_id"], "state": job["state"],
                    "pause_reason": job["pause_reason"], "resume_at": job["resume_at"],
                    "metrics": stored.get("metrics")}

        if name == "list_leads":
            sql = "SELECT * FROM leads WHERE 1=1"
            params = []
            if args.get("job_id"):
                sql += " AND job_id=?"
                params.append(args["job_id"])
            if args.get("stage"):
                sql += " AND stage=?"
                params.append(args["stage"])
            sql += " ORDER BY score DESC LIMIT ?"
            params.append(int(args.get("limit") or 15))
            rows = db.query(sql, params)
            return {"count": len(rows),
                    "leads": [_compact_lead(r) for r in rows]}

        if name == "verify_email":
            result = VerificationPipeline(router).verify(args.get("email", ""))
            return {"email": args.get("email"), "status": result.get("status"),
                    "confidence": result.get("confidence"),
                    "via": result.get("via") or result.get("provider"),
                    "reason": (result.get("details") or {}).get("reason")}

        if name == "system_status":
            registry_rows = router.status_report()
            providers = {}
            for r in registry_rows:
                key_state = "local" if r["env_key"] is None else (
                    "set" if __import__("os").environ.get(r["env_key"]) else "missing")
                providers[f"{r['name']}:{r['task']}"] = {
                    "status": r["status"], "key": key_state,
                    "used": r["quota_used"], "limit": r["quota_limit"]}
            jobs = {j["state"]: j["n"] for j in
                    db.query("SELECT state, COUNT(*) AS n FROM jobs GROUP BY state")}
            leads = {l["stage"]: l["n"] for l in
                     db.query("SELECT stage, COUNT(*) AS n FROM leads GROUP BY stage")}
            return {"providers": providers, "jobs": jobs, "leads": leads}

        return {"error": f"أداة غير معروفة: {name}"}
    except NoProviderAvailable as exc:
        return {"error": "لا يوجد مزوّد متاح لهذه العملية الآن",
                "detail": str(exc),
                "fix": "أضف مفتاحًا صالحًا من تبويب المفاتيح (مثلاً Gemini أو Tavily)"}
    except Exception as exc:  # never crash the conversation
        return {"error": f"{type(exc).__name__}: {exc}"}


def run_agent(router, db, messages: list) -> dict:
    """One user turn -> up to MAX_STEPS tool rounds -> final Arabic reply."""
    contents = []
    for m in messages[-12:]:
        role = "model" if m.get("role") == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": str(m.get("content", ""))}]})
    flat = "\n".join(f"{m.get('role')}: {m.get('content')}" for m in messages[-6:])

    tool_trace = []
    try:
        for _step in range(MAX_STEPS):
            payload = {
                "contents": contents,
                "system_instruction": SYSTEM_INSTRUCTION,
                "tools": TOOLS_DECL,
                "prompt": flat,
                "json_mode": False,
            }
            result, meta = router.route("reasoning", payload, use_cache=False)
            fcs = result.get("function_calls") or []
            if not fcs:
                return {"reply": result.get("text", "") or "…",
                        "provider": meta.get("provider"), "tools": tool_trace}
            # echo the model's parts back VERBATIM (thoughtSignature in
            # functionCall parts is required by gemini-3.x)
            contents.append({"role": "model",
                             "parts": [fc.get("_raw") or
                                       {"functionCall": {"name": fc["name"],
                                                         "args": fc.get("args") or {}}}
                                       for fc in fcs]})
            responses = []
            for fc in fcs:
                out = execute_tool(fc["name"], fc.get("args") or {}, router, db)
                compact = json.dumps(out, ensure_ascii=False, default=str)
                tool_trace.append({
                    "name": fc["name"], "args": fc.get("args") or {},
                    "ok": "error" not in out,
                    "summary": compact[:220],
                })
                responses.append({"functionResponse": {
                    "name": fc["name"],
                    "response": json.loads(compact) if len(compact) < 20000 else {"result": compact[:20000]},
                }})
            contents.append({"role": "user", "parts": responses})
        return {"reply": "وصلت الحد الأقصى لخطوات تنفيذ الأدوات — جرّب تطلب النتيجة على دفعات.",
                "tools": tool_trace}
    except NoProviderAvailable as exc:
        return {"reply": "مفيش مزوّد LLM متاح دلوقتي — أضف مفتاح Gemini من تبويب المفاتيح "
                         "أو استنى انتهاء فترة التبريد.",
                "detail": str(exc), "tools": tool_trace}
