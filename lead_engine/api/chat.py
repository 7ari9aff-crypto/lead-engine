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

# Scope tag for each tool — used by agent tool_policy to decide which tools
# an agent is allowed to call (multi-tenant safety).
TOOL_SCOPES = {
    "run_lead_generation": ["jobs:run", "leads:write"],
    "get_job_status": ["jobs:read"],
    "list_leads": ["leads:read"],
    "verify_email": ["verification:run"],
    "system_status": ["system:read"],
    "start_research": ["jobs:run", "search:read", "evidence:write"],
    "define_icp": ["system:read", "jobs:run"],
    "get_research_progress": ["jobs:read"],
    "answer_research_question": ["jobs:run", "evidence:write"],
    "resume_research_job": ["jobs:run"],
}

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
        {
            "name": "define_icp",
            "description": "حدّد معايير الفلترة (من ينفع ومن لا ينفع) — يحول شروطك لنسخة ICP فعلية وتُنشَّط لكل البحث والتأهيل القادم.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "industry": {"type": "STRING", "description": "القطاع المستهدف"},
                    "cities": {"type": "ARRAY", "items": {"type": "STRING"},
                               "description": "المدن المستهدفة"},
                    "keywords_en": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "keywords_ar": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "min_branches": {"type": "INTEGER"},
                    "notes": {"type": "STRING", "description": "شروط إضافية حرة من المستخدم"},
                },
                "required": ["industry"],
            },
        },
        {
            "name": "get_research_progress",
            "description": "استعلم عن تفاصيل وتقدم مهمة بحث وكيلية (العدادات، الحقائق الموثقة، التعارضات، مرحلة الإنجاز).",
            "parameters": {
                "type": "OBJECT",
                "properties": {"job_id": {"type": "STRING", "description": "معرف مهمة البحث"}},
                "required": ["job_id"],
            },
        },
        {
            "name": "answer_research_question",
            "description": "أجب على سؤال مفتوح طرحه وكيل البحث (حالة WAITING_FOR_USER) لاستئناف البحث تلقائيًا.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "job_id": {"type": "STRING", "description": "معرف مهمة البحث"},
                    "answer": {"type": "STRING", "description": "إجابة المستخدم على السؤال المطروح"},
                },
                "required": ["job_id", "answer"],
            },
        },
        {
            "name": "resume_research_job",
            "description": "استأنف مهمة بحث وكيلية متوقفة مؤقتًا (PAUSED) أو اطلب تعميق البحث (RESEARCH_MORE) من مرحلة المراجعة.",
            "parameters": {
                "type": "OBJECT",
                "properties": {"job_id": {"type": "STRING", "description": "معرف مهمة البحث"}},
                "required": ["job_id"],
            },
        },
        {
            "name": "start_research",
            "description": "ابدأ مهمة بحث وكيلية دائمة عن هدف صيغ بلغة طبيعية (مثال: دور على شركات SaaS في السعودية بين 100 و500 موظف). المهمة تبحث وتحقق وتوثق الحقائق بمصادرها ويتوقف عند مراجعتك — لا يرسل شيئًا لأحد.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "objective": {"type": "STRING",
                                  "description": "هدف البحث بلغة طبيعية كما كتبه المستخدم"},
                },
                "required": ["objective"],
            },
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
            if hasattr(db, "execute"):
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
            summary, metrics, _outputs = run_benchmark(icp, write=False)
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

        if name == "define_icp":
            from ..icp_store import ICPStore

            definition = {
                "industry": args.get("industry") or "general",
                "cities": [{"name": c} for c in (args.get("cities") or [])],
                "keywords_en": args.get("keywords_en") or [args.get("industry")],
                "keywords_ar": args.get("keywords_ar") or [],
                "criteria": {"min_branches": args.get("min_branches") or 0,
                             "notes": args.get("notes") or ""},
                "v0_limits": {"max_search_queries": 6,
                              "search_results_per_query": 8,
                              "enrichment_budget_credits": 0,
                              "enrichment_max_people": 0},
            }
            icps = ICPStore(db)
            row = icps.create_version("agentic", definition, source="chat_intent")
            row = icps.activate(row["icp_version_id"])
            return {"icp_version_id": row["icp_version_id"], "status": "ACTIVE",
                    "definition": definition,
                    "note": "معاييرك بقت هي فلتر البحث والتأهيل — أطلب requalify "
                            "في أي وقت لإعادة تقييم الـleads المخزنة عليها."}

        if name == "get_research_progress":
            from ..research import ResearchJobManager
            job_id = args.get("job_id")
            if not job_id:
                return {"error": "job_id مطلوب"}
            return ResearchJobManager(db).progress(job_id)

        if name == "answer_research_question":
            from ..research import ResearchJobManager
            from ..truth import FactsStore
            from ..db import utcnow
            from ..queue import enqueue, platform_mode

            job_id = args.get("job_id")
            answer = (args.get("answer") or "").strip()
            if not job_id or not answer:
                return {"error": "job_id و answer مطلوبان"}
            manager = ResearchJobManager(db)
            if manager.jobs.current(job_id) != "WAITING_FOR_USER":
                return {"error": f"المهمة في حالة {manager.jobs.current(job_id)} وليست في انتظار المستخدم"}
            store = FactsStore(db)
            open_qs = store.open_questions(job_id)
            if open_qs:
                store.drop_open_question(open_qs[-1]["id"])
            db.execute(
                "INSERT INTO job_events (ts, job_id, from_state, to_state, reason)"
                " VALUES (?,?,?,?,?)",
                (utcnow(), job_id, "WAITING_FOR_USER", "RUNNING", f"user answered in chat: {answer[:300]}"))
            manager.jobs.transition(job_id, "RUNNING")
            if platform_mode():
                enqueue(db, job_id)
            else:
                import threading
                def _run():
                    from ..config import load_settings
                    from ..db import Database
                    from ..research.orchestrator import ResearchOrchestrator
                    # clone the request's DB handle: a background thread must
                    # never share one sqlite connection with the request loop
                    thread_db = Database(db.path) if getattr(db, "dialect", "sqlite") == "sqlite" else db
                    thread_db.org_id = getattr(db, "org_id", None)
                    try:
                        ResearchOrchestrator(thread_db, load_settings(), job_id).run()
                    finally:
                        if thread_db is not db:
                            thread_db.close()
                threading.Thread(target=_run, daemon=True).start()
            return {"ok": True, "state": "RUNNING", "message": "تم تسجيل الإجابة واستئناف البحث بنجاح."}

        if name == "resume_research_job":
            from ..research import ResearchJobManager
            from ..queue import enqueue, platform_mode

            job_id = args.get("job_id")
            if not job_id:
                return {"error": "job_id مطلوب"}
            manager = ResearchJobManager(db)
            state = manager.jobs.current(job_id)
            if state == "PAUSED":
                manager.jobs.resume(job_id)
            elif state == "READY_FOR_REVIEW":
                manager.jobs.transition(job_id, "RUNNING", "RESEARCH_MORE")
            else:
                return {"error": f"المهمة في حالة {state} ولا يمكن استئنافها"}
            if platform_mode():
                enqueue(db, job_id)
            else:
                import threading
                def _run():
                    from ..config import load_settings
                    from ..db import Database
                    from ..research.orchestrator import ResearchOrchestrator
                    # clone the request's DB handle: a background thread must
                    # never share one sqlite connection with the request loop
                    thread_db = Database(db.path) if getattr(db, "dialect", "sqlite") == "sqlite" else db
                    thread_db.org_id = getattr(db, "org_id", None)
                    try:
                        ResearchOrchestrator(thread_db, load_settings(), job_id).run()
                    finally:
                        if thread_db is not db:
                            thread_db.close()
                threading.Thread(target=_run, daemon=True).start()
            return {"ok": True, "state": "RUNNING", "message": "تم استئناف مهمة البحث بنجاح."}

        if name == "start_research":
            objective = (args.get("objective") or "").strip()
            if not objective:
                return {"error": "objective مطلوب"}
            from ..icp_store import ICPStore
            from ..queue import enqueue, platform_mode
            from ..research import ResearchJobManager

            manager = ResearchJobManager(db)
            active_icp = ICPStore(db).active("agentic")
            job_id = manager.create(
                objective,
                icp_version_id=active_icp["icp_version_id"] if active_icp else None)
            if platform_mode():
                enqueue(db, job_id)
                mode = "queue"
            else:
                # inline: a daemon thread runs the orchestrator on a CLONE of
                # this request's database (same backend, same tenant) — never
                # on a fresh handle that would point at another store
                import threading

                org = getattr(db, "org_id", None)

                def _run():
                    from ..config import load_settings
                    from ..research.orchestrator import ResearchOrchestrator

                    if getattr(db, "dialect", "sqlite") == "sqlite":
                        from ..db import Database

                        orch_db = Database(db.path)
                        orch_db.org_id = org or "shared"
                    else:
                        from ..db import open_db

                        orch_db = open_db(org_id=org)
                    try:
                        ResearchOrchestrator(orch_db, load_settings(), job_id).run()
                    finally:
                        orch_db.close()

                threading.Thread(target=_run, daemon=True).start()
                mode = "inline"
            return {"job_id": job_id, "state": "QUEUED", "mode": mode,
                    "note": "مهمة بحث دائمة بدأت — تابع تقدمها الحي في صفحة "
                            "المهام، وبتتوقف عند مراجعتك قبل أي إجراء."}

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


def run_agent(router, db, messages: list, provider: str | None = None,
              enabled_tools: list | None = None,
              agent_slug: str | None = None) -> dict:
    """One user turn -> up to MAX_STEPS tool rounds -> final Arabic reply.
    provider: pin the model (chat model picker). enabled_tools: subset of the
    tool names to expose this turn (integrations picker); None = all.
    agent_slug: name of the agent row in `agents` table — its active version's
    instructions + tool_policy drive the system prompt + tool filter. Falls back
    to SYSTEM_INSTRUCTION + all tools when omitted (backwards compatible)."""
    contents = []
    for m in messages[-12:]:
        role = "model" if m.get("role") == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": str(m.get("content", ""))}]})
    flat = "\n".join(f"{m.get('role')}: {m.get('content')}" for m in messages[-6:])

    # ---- Resolve agent config (DB-driven) ----
    system_instruction = SYSTEM_INSTRUCTION
    if agent_slug:
        try:
            from ..agent_registry import AgentRegistry
            payload = AgentRegistry(db).get_active_version(agent_slug)
        except Exception:
            payload = None
        if payload:
            version_row = payload["version"]
            agent_row = payload["agent"]
            custom = (version_row or {}).get("instructions")
            if custom:
                # Keep the role framing consistent — wrap any user instructions
                # with the same identity header so the model still knows who it is.
                system_instruction = (
                    f"أنت \"{agent_row.get('name') or agent_slug}\" — {agent_row.get('description') or 'مساعد متخصص'}\n\n"
                    f"{custom}"
                )
            # Filter the toolset by the agent's tool_policy.scopes if present.
            scopes = ((version_row or {}).get("tool_policy") or {}).get("scopes")
            if scopes and enabled_tools is None:
                # Each tool declares its scopes; intersect with the agent's allowed scopes.
                allowed_scopes = set(scopes)
                allowed = {name for name, tool_scopes in TOOL_SCOPES.items()
                           if set(tool_scopes) & allowed_scopes}
                enabled_tools = list(allowed) or None

    tools_decl = TOOLS_DECL
    if enabled_tools is not None:
        allowed = set(enabled_tools)
        decls = [d for d in TOOLS_DECL[0]["function_declarations"] if d["name"] in allowed]
        tools_decl = [{"function_declarations": decls}] if decls else None

    tool_trace = []
    try:
        for _step in range(MAX_STEPS):
            payload = {
                "contents": contents,
                "system_instruction": system_instruction,
                "tools": tools_decl,
                "prompt": flat,
                "json_mode": False,
            }
            result, meta = router.route("reasoning", payload, use_cache=False,
                                        prefer_provider=provider)
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
