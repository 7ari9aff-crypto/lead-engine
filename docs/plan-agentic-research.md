# Agentic Research Platform — خطة التنفيذ المعتمدة (R0–R6)

> اعتمدت 2026-09-13. المرجع: الـdirective النهائي (Chat-first autonomous research agent).
> المبدأ الملزم: **extension فوق الموجود — ممنوع أي نظام موازٍ**. أي تعارض مع
> `docs/architecture.md` يحسم لصالح الوكيل الذاتي + القرار البشري، ويوثق هنا.

## الهدف في سطر

وكيل بحث ذاتي يبدأ من محادثة بالعربي: يفهم الهدف، يخطط، يبحث من مصادر متعددة،
يحقق بعمق (browsing عبر OpenManus)، يحوّل الملاحظات إلى **verified facts بمصادرها**،
يكشف التعارض والشك والقِدم بصراحة، يقيّم على ICP مُصدَّر، ويتوقف عند
**READY_FOR_REVIEW** حيث المستخدم — لا الوكيل — يقرر:
`APPROVE_CONTACT / REJECT / RESEARCH_MORE / SAVE_FOR_LATER`.
**APPROVE_CONTACT هو آخر حد في النظام الحالي — لا يوجد أي outbound execution.**

## خريطة المكونات

### KEEP (يُستخدم كما هو)
- Provider Router + Registry + usage_ledger (Model Gateway — لا silent downgrade للمهام المثبتة)
- Agent Registry/Versions/Runs/Steps/Approvals (سلطة الموافقة بشرية 100%)
- Tenancy/Auth (middleware، حقن org، RLS)، Cache 3-level، Dedup، Email Verification،
  Legal Gate، Events/Outbox/Webhooks، Queue (SKIP LOCKED)، MCP، Supabase dual-dialect.
- الـpipeline الحالي يظل مسارًا deterministic/benchmark — أدواته تُستدعى كخدمات.

### EXTEND/REFACTOR
- `chat.py` → orchestrator وكيلي (intent → plan → tools → observations → replanning).
- `discovery/icp` → أدوات بحث متعددة المصادر؛ الـplanner القديم fallback.
- `qualification/filters` → تأهيل هجين: قواعد deterministic + reasoning مسنود بالـfacts.
- `orchestrator.py` → مراحله خدمات قابلة للاستدعاء.
- `evidence` → طبقة Truth كاملة (research_facts/conflicts/freshness).

## حالات الـResearch Job (النظام الجديد)

QUEUED → RUNNING → DISCOVERING → RESEARCHING → VERIFYING → QUALIFYING
→ READY_FOR_REVIEW → COMPLETED
فروع: PAUSED (= WAITING_FOR_CAPACITY، موجود أصلًا)، WAITING_FOR_USER (سؤال مفتوح
يمنع التقدم)، CANCELLED (بأمر المستخدم فقط)، FAILED (خطأ غير قابل للاسترداد).
كل انتقال يُسجل في job_events + stop_reason عند أي توقف.

## Business Truth — قواعد صارمة

1. النموذج ليس مصدر الحقيقة. المصدر: facts + evidence + provenance + freshness + policy.
2. حالات الحقيقة فقط: `VERIFIED | CONFLICTED | STALE | UNVERIFIED | INFERRED`.
   ممنوع "probably true". مفيش قيمة بلا مصدر إلا INFERRED (مع سبب مسجل).
3. VERIFIED يتحقق بـ: مصدرين مستقلين (دومينان مختلفان) أو أداة تحقق صريحة.
4. كل fact لها collected_at/expires_at (من cache_policy). القديم يُعرض STALE —
   الكاش القديم لا يتحول لـverified fresh أبدًا.
5. التعارض لا يُحل بصمت: قيمتان → CONFLICTED + صف في fact_conflicts؛ الحل
   (auto بمصدر أقوى أو بشري) يوثق بمن/متى/لماذا. غير المحلول يبقى OPEN ويظهر.

## الصلاحيات

Tool capability ≠ permission. كل أداة لها scopes وتُفحص وقت التنفيذ لا عند الإعلان.
الوكيل ينفذ: SEARCH / RESEARCH / ENRICH / VERIFY / QUALIFY / SAVE / PRESENT.
الوكيل **لا يستطيع** مطلقًا: SEND_EMAIL / SEND_WHATSAPP / SEND_LINKEDIN، ولا
APPROVE_CONTACT — القرارات البشرية endpoints بمصادقة، غير معرّضة كأدوات للـLLM.

## Budgets & Stop (لكل job — guardrails لا workflow)

max_steps / max_tool_calls / max_searches / max_model_calls / max_time_minutes /
max_candidates — defaults في settings.yaml، override لكل job. الأداة تُرفض عند
استنفاد الحد والjob ينتقل READY_FOR_REVIEW (أو PAUSED للسعة) مع stop_reason موثق:
`OBJECTIVE_SATISFIED | COVERAGE_ADEQUATE | DIMINISHING_RETURNS | BUDGET_EXHAUSTED |
USER_STOPPED | WAITING_USER_INPUT | NO_CAPACITY`.

## Model Strategy

`planning/replanning` → نموذج مثبت من agent_version (prefer_provider) — لو غير
متاح: PAUSED بـNO_CAPACITY، **لا هبوط صامت**. `extraction/classification` → pool
رخيص مسموح. البحث → search providers. الـbrowsing → OpenManus runtime خارجي.

## OpenManus (R4) — contract خارجي

خدمة REST منفصلة على جهاز المستخدم: `POST /tasks` (browse/research) → task_id،
`GET /tasks/{id}` → status + extracted facts + sources + quotes. المصادقة
`Bearer OPENMANUS_TOKEN`. مفتاحه المستقل — خارج حدود الثقة. غير متاح؟ الأداة
تتصفى بصدق وتظهر UNKNOWN، والوكيل يكتفي بمقتطفات البحث.

## المراحل

| المرحلة | المحتوى | DoD |
|---|---|---|
| R0 | تجميد هذه الوثيقة + قرار في architecture.md | وثيقتان معتمدتان |
| R1 | Truth Layer: research_facts/fact_sources/fact_conflicts/open_questions/visited_sources/icp_versions + FactsStore + RLS | كل fact لها مصدر وحالة وقِدم؛ التعارض يُكشف ويُحل/يبقى OPEN |
| R2 | Research jobs: الحالات الجديدة + research_context دائم + budgets + stop_reason + cancel | job يعيش عبر restart و429؛ budgets توقف بـstop_reason |
| R3 | Orchestrator وكيلي + أدوات scoped + سرد تقدم عربي + replanning | تجربة الشات (مرشحون→dedup→تعارضات→fit) شغالة |
| R4 | OpenManus client + registry + wrapper جاهز للجهاز الثاني + contract | research_company يستدعي runtime خارجي ويحول النتائج facts |
| R5 | Stage 3: presentation payload + القرارات الأربعة + RESEARCH_MORE يستأنف السياق + re-qualification من facts | بطاقة تفسير كاملة لكل lead + قرار بشري محفوظ ومؤثر |
| R6 | E2E + observability لكل job + audit trail + DoD checklist + handoff | كل بنود الـDoD تعدي بنًدا بندًا باختبار فعلي |

## Invariants (لا تُكسر أبدًا)

- مفيش outbound: لا إرسال إيميل/واتساب/لينكدإن في أي مرحلة. APPROVE_CONTACT terminal.
- 165 اختبار قديمة تبقى خضراء بعد كل مرحلة + كل مرحلة لها اختباراتها الجديدة.
- الـSQL بـ`?` placeholders؛ جداول المنصة public.* عبر `_t()`؛ جداول التشغيل engine.* bare.
- كل جدول تجاري جديد: organization_id + RLS + إدخاله في ORG_TABLES بـdb_pg.
- الـaliases القديمة للـAPI محفوظة (n8n). الجديد تحت `/api/v1/`.
- ICP versioned في DB (icp_versions) — YAML يظل import source فقط.
- كل قرار مهم (decision/conflict resolution/budget stop) في audit_logs.
