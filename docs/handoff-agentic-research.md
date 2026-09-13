# Handoff — Agentic Research Platform (R0–R6)

تاريخ التسليم: 2026-09-13 · المرجع: docs/plan-agentic-research.md + الـdirective

## ما بُني (طبقة طبقة)

| المرحلة | المكونات | ملفات |
|---|---|---|
| R0 | تجميد الهدف + قرار المعمارية | docs/plan-agentic-research.md, docs/architecture.md §8 |
| R1 | Truth Layer: facts بحالات الخمسة + provenance + تعارضات + freshness + ICP versioned | lead_engine/truth.py, icp_store.py, migrations 000001+000002 |
| R2 | Research jobs دائمة: حالات موسعة + context + budgets + stop_reason + cancel | lead_engine/jobs.py, research/manager.py, migration 000003+000004 |
| R3 | Orchestrator وكيلي: planner + جولات + أدوات scoped + سرد + worker dispatch + API | lead_engine/research/{orchestrator,tools,qualification}.py, api/research_api.py |
| R4 | OpenManus: contract موثق + عميل + wrapper جاهز للنشر على جهاز آخر | docs/openmanus-contract.md, lead_engine/research/openmanus.py, wrapper/ |
| R5 | Stage 3: presentation + تماديةل الـleads + القرارات الأربعة + RESEARCH_MORE + requalify + UI | research/presentation.py, api/review_api.py, web/src/components/review/ReviewPanel.tsx |
| R6 | E2E + observability لكل job + audit + تشغيل دخان حقيقي | tests/test_e2e_research.py + manager.progress observability |

## إعادة الاستخدام (صفر هدم)

Provider Router/Registry/Quotas · Agent Registry/Versions/Runs/Steps/Approvals ·
Tenancy+RLS · Cache · Dedup · Email Verification · Legal Gate · Events/Outbox ·
Queue (SKIP LOCKED) · MCP · Supabase dual-dialect — كلها KEEP واستُخدمت كما هي.
الـpipeline القديم شغال كمسار deterministic/benchmark.

## المايجريشنز (مطبقة على Supabase الحية + auto-migration لـSQLite القديمة)

1. `20260913000001_truth_layer.sql` — research_facts/fact_sources/fact_conflicts/open_questions/visited_sources/icp_versions + disposition columns + RLS
2. `20260913000002_truth_rls_tighten.sql` — fail-closed WITH CHECK (لا NULL-org escape) + فهرس coalesce-uuid
3. `20260913000003_research_jobs.sql` — research_context + RLS
4. `20260913000004_research_context_run.sql` — run_id
   تم التحقق سلوكيًا: عزل تينانت كامل (A يرى صفه، B وبدون سياق = 0)، تحديث عابر مسدود، كتابة بلا سياق مرفوضة.

## الـAPIs/الأدوات الجديدة

- `POST/GET /api/v1/research[/{id}]` + `/cancel` `/answer` `/resume` + `/events`
- `GET /api/v1/review/pending?job_id=` — لوحة المراجعة
- `GET /api/v1/leads/{id}/presentation` — طبقة التفسير
- `POST /api/v1/leads/{id}/decision` — القرارات الأربعة (APPROVE_CONTACT terminal)
- `POST /api/v1/leads/{id}/requalify` — إعادة تأهيل من facts (صفر discovery)
- أدوات الوكيل (8): search_companies, research_company, save_fact, verify_fact, list_facts, qualify_lead, get_research_status, ask_user — **لا توجد أي أداة send/approve**
- الشات: أداة `start_research` (chat-first)

## متغيرات البيئة الجديدة

`OPENMANUS_BASE_URL` + `OPENMANUS_TOKEN` (اختياريان — بدونهما الأداة تتصفى بصدق).
(الكاملة في docs/openmanus-contract.md وwrapper/README.md)

## نتائج الاختبار

- **244 passed, 2 skipped** (كانت 165 — مفيش اختبار قديم ااتكسر)
- E2E كامل: شات → job → بحث → حفظ facts بمصادر → تحقق → تأهيل → ماديةلة → عرض → قرارات → RESEARCH_MORE → requalify → audit
- **تشغيل دخان حقيقي** (مفاتيح فعلية Gemini+Tavily): job حقيقي أنتج 4 leads ماديةلة وصلت بوابة المراجعة + APPROVE_CONTACT مدقق — اكتشف وأصلح 3 فجوات تكامل حقيقية (قائمة الأدوات في البرومبت، حلقة الـobservations المقفولة، إقفال الـbudget عبر التأهيل)

## أمان

- مفيش أسرار في الفرونت؛ المفاتيح .env/credentials مشفرة؛ الاختبارات معزولة عن المفاتيح الحقيقية (conftest guardrail)
- RLS سلوكيًا متحقق على الإنتاج؛ القرارات البشرية غير قابلة للاستدعاء من أي نموذج

## DoD checklist — الحالة الفعلية

متحقق ✅: truth layer · evidence/provenance · conflicts · freshness · persistent jobs · restart/resume · budgets · orchestration · tools scoped · facts→evidence · qualification من facts · human review · القرارات الأربعة · RESEARCH_MORE سياق · re-verification · APPROVE_CONTACT terminal · لا outbound · RLS · observability · audit للقرارات · 244 اختبار · E2E · recovery scenarios

قيود معروفة (حقيقية، موثقة):
1. **OpenManus الحية**: العقد + العميل + الـwrapper جاهزين ومختبرين بوحدات؛ الربط الفعلي ينتظر تشغيل الـwrapper على جهازك (خطوات جاهزة في wrapper/README.md)
2. **حل تعارضات بالـAPI**: `resolve_conflict` موجود في الطبقة الداخلية، endpoint بشري مخصص له لم يُبنَ بعد (التعارضات معروضة في العرض والقرار عليها عبر RESEARCH_MORE)
3. **جودة الاستخراج**: في الـsmoke الحقيقي حفظ الوكيل حقول المدينة فقط — تحسين البرومبت لشمول الحفظ مساحة تحسين مستمرة (بنية الحفظ والتوثيق تعمل)
4. **سرد الشات**: polling كل 5 ثوانٍ (لا SSE)
5. **النشر على Vercel**: خطوة يدوية عليك (CI يبني الفرونت تلقائيًا)
