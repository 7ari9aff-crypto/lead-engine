# تقرير التنفيذ الكامل — نظام البحث الوكيلي (مبني على الكود فعليًا)

تاريخ التقرير: 2026-09-13 · القاعدة: commit `6c2340e..d70efde` على `main`
كل رقم وكل سطر في التقرير ده متحقق من الكود الحالي في الريبو.

## 1) الملخص التنفيذي

بنينا طبقة وكيل بحث ذاتي **فوق** النظام الموجود بدون هدم أي مكوّن: من كلامك
بالعربي → مهمة بحث دائمة → جمع موثق → فلترة بمعاييرك → عرض بالأسباب → قرارك
الوحيد. الفرق الكلي: **48 ملف، +5,740 سطر** في 12 commit، و**246 اختبار
ناجح + 2 متخطيين** (كانت 165) + E2E كامل + تشغيلان حقيقيان بمفاتيح فعلية.

## 2) الخط الزمني (commits على main)

| Commit | المرحلة | المحتوى |
|---|---|---|
| `471f791` | R0 | تجميد الهدف: docs/plan-agentic-research.md + قرار §8 في docs/architecture.md |
| `fb4f9e6` | R1 | Truth Layer: 6 جداول + FactsStore + ICPStore (migration 000001) |
| `0d15b57` | R1 fix | 15 ملاحظة مراجعة هندسية: MAX()→CASE، إلزام provenance، كشف تعارض في مسار التحديث، RLS مشدد (migration 000002) |
| `0fff149` | R2 | آلة حالات موسعة + research_context + ResearchJobManager (migration 000003) |
| `3ae8007` | R3 | Orchestrator + 8 أدوات scoped + API البحث + worker dispatch + حماية اختبارات من المفاتيح الحقيقية |
| `b2287b9` | R4 | OpenManus: عقد + عميل + wrapper + ترقية seeding تلقائية |
| `a1fe246` | R5 | presentation + تماديةل الـleads + القرارات الأربعة + requalify + audit |
| `2c34e74` | R5 UI | ReviewPanel في صفحة الـleads + أداة start_research للشات + static build |
| `77e6cbf` | R6 | قفل حلقة الملاحظات + توثيق الأدوات في البرومبت + إقفال الـbudget عبر التأهيل + تشغيل دخان حقيقي 1 |
| `9ab907c`,`d70efde` | — | handoff + تحديث بعد مراجعتك |
| `fed1e56` | تكملة 1/2 | معاييرك كـICP API + define_icp للشات + استخراج تلقائي + بوابة الأدلة (migration 000004) — تشغيل دخان حقيقي 3 |

## 3) خريطة الكود الجديد (بالأسطر)

| الملف | الأسطر | الدور |
|---|---|---|
| `lead_engine/truth.py` | 521 | طبقة الحقيقة: FactsStore كامل |
| `lead_engine/research/orchestrator.py` | 470 | حلقة الوكيل: تخطيط/تنفيذ/إقفال |
| `lead_engine/research/tools.py` | 343 | 8 أدوات + إلزام الصلاحيات |
| `lead_engine/api/review_api.py` | 224 | Stage 3: العرض + القرارات الأربعة |
| `wrapper/openmanus_wrapper.py` | 221 | خدمة OpenManus للجهاز التاني |
| `lead_engine/research/manager.py` | 272 | مهام البحث الدائمة + الموازين |
| `lead_engine/db.py` | 504 | +6 جداول SQLite + auto-migrations + audit() |
| `lead_engine/api/research_api.py` | 183 | REST مهام البحث |
| `lead_engine/research/qualification.py` | 146 | التأهيل المسنود بالأدلة |
| `lead_engine/research/openmanus.py` | 104 | عميل الـruntime |
| `lead_engine/api/icp_api.py` | 67 | معاييرك كـICP versioned |
| `lead_engine/research/presentation.py` | 120 | طبقة التفسير |
| `lead_engine/icp_store.py` | 117 | إصدارات الـICP |
| `web/src/components/review/ReviewPanel.tsx` | ~215 | لوحة القرار في الواجهة |

## 4) المرحلة 1 — جمع البيانات (الكود الفعلي)

**نقطة الدخول**: `POST /api/v1/research` → `create_research` (api/research_api.py:67)
→ `ResearchJobManager.create` (research/manager.py:58) ينشئ صف jobs + صف
research_context (objective, icp_version_id, budgets, counters).

**الحلقة الوكيلية** (research/orchestrator.py:116 `_loop`):
1. لا خطة؟ → `_make_plan` (:378) يحوّل الهدف لاستعلامات عبر الـLLM (json_mode).
2. كل جولة: `_agent_turn` (:165) يبني بروميت فيه الهدف + الخطة + التقدم +
   **نتائج أدوات الجولة السابقة** (الملاحظات) + **قائمة الأدوات الحرفية**
   (TOOLS_DOC — tools.py:288، كانت ناقصة وكشفتها التشغيلة الحقيقية).
3. النموذج يرد JSON أفعال → `execute_tool` (tools.py:317) يفحص **الصلاحيات
   وقت التنفيذ** (ScopeDenied) + الموازين، ويسجل كل نداء كـagent_step.

**أدوات الجمع**:
- `search_companies` (tools.py:70): بحث حقيقي عبر Router → لكل نتيجة
  **استخراج حتمي** للهاتف/الإيميل بـ`extract_contacts` (pipeline/normalize.py:73)
  وحفظهم فورًا كحقائق بمصدر رابط النتيجة (`record_fact`) — الجمع مش رهين
  بذاكرة النموذج.
- `research_company` (tools.py:136): التعميق عبر OpenManus
  (research/openmanus.py:104 — عقد REST في docs/openmanus-contract.md،
  والـwrapper للجهاز التاني في wrapper/openmanus_wrapper.py:221). غير مهيأ؟
  يرجّع `UNAVAILABLE` بصدق — ممنوع الاختراع.
- هوية ثابتة للمرشح: `canonical_subject` (tools.py:57) — الدومين أصلًا،
  وإلا slug من الاسم، فنفس الشركة من مصادر مختلفة = موضوع واحد.

**كل حقيقة تُكتب عبر** `FactsStore.record_fact` (truth.py:118): نفس القيمة
→ تحديث عمرها وإضافة مصدر؛ قيمة جديدة fresh → **تعارض مفتوح**
(`_detect_conflicts` :200 + fact_conflicts)؛ قيمة قديمة منتهية → تستبدل
بدون تعارض. مفيش قيمة بدون مصدر إلا `inferred=True` مع سبب في quote.

## 5) المرحلة 2 — الفلترة (الكود الفعلي)

**معاييرك أولًا**: `POST /api/v1/icps` (api/icp_api.py:49) أو أداة الشات
`define_icp` (api/chat.py) — تنشئ نسخة ICP وتنشطها (icp_store.py). الفلترة
الحتمية والتأهيل بيقراو **النسخة النشطة** دايمًا.

**الفلترة الحتمية قبل أي نموذج** — `deterministic_checks`
(research/qualification.py:50): مدينة VERIFIED خارج مدن الـICP = رفض فوري
بدرجة 0 (fit_score=0, deterministic=True) بدون استهلاك LLM.

**التأهيل المسنود بالأدلة** — `qualify_from_facts` (qualification.py:80):
يقرأ `facts_for_qualification` (truth.py:445) — القيم + حالاتها + المتعارض +
القديم — ويمنع النموذج من اختراع أي شيء خارجها (unknown_fields إلزامية
للمجهول).

**حالات الحقيقة الخمسة** تُشتق بـ`_recompute_status` (truth.py:346):
مصدرين مستقلين بدومينين مختلفين = VERIFIED؛ مصدر واحد = UNVERIFIED؛ بلا
مصدر = INFERRED؛ تعارض مفتوح = CONFLICTED (يتغلب على الكل)؛ منتهي = STALE.
التحقق الصريح `verify_fact` (:292) والتاريخ الناجح في `resolve_conflict`
(:263) **لا يُخفضان صمتًا**.

**بعد التوقف** — `_finalize` (orchestrator.py:229): مسح تحقق إيميلات
(`_verify_emails` :251 بالسلسلة 5-حالات) → تأهيل كل مرشح (`_qualify_all`
:275 بترتيب حتمي) → **تماديةل** (`_materialize_leads` :307):
- **بوابة الأدلة**: مرشح بلا جهة اتصال وأقل من حقلين = مستبعد (يتسجل في
  عداد thin_candidates_skipped) — الدلائل والصفحات الشاردة ما توصلكش.
- LegalGate (pipeline/legal_gate.py) يقرر التخزين، وScorer يحسب الدرجة.
- stage=REVIEW دائمًا — القرار لك.

**عند التوقف** دايمًا stop_reason موثق: OBJECTIVE_SATISFIED /
COVERAGE_ADEQUATE / DIMINISHING_RETURNS (3 جولات بلا مرشحين جدد) /
BUDGET_EXHAUSTED / USER_STOPPED — وحتى توقف الموازين **يعدي بالإقفال**
(تحقق + تأهيل + تماديةل) قبل بوابة المراجعة.

## 6) المرحلة 3 — العرض والقرار (الكود الفعلي)

**طبقة التفسير** — `build_presentation` (research/presentation.py:67):
identity بكل حقل وحالته + fit (score/tier/why/confidence) + verification
(verified_facts + تغطية الاتصال) + facts_snapshot كامل بمصادره +
missing_information (:58) + conflicts + stale_fields + sources_count.

**الوصول**: `GET /api/v1/review/pending?job_id=` (api/review_api.py:77)
للوحة كاملة، و`GET /api/v1/leads/{id}/presentation` (:100) لعميل واحد.
الواجهة: `ReviewPanel` (web/src/components/review/ReviewPanel.tsx) داخل
drawer صفحة الـLeads — يعرض كل ده بأزرار القرار.

**القرار البشري** — `lead_decision` (review_api.py:106):
APPROVE_CONTACT / REJECT / RESEARCH_MORE / SAVE_FOR_LATER — pattern-validated
(422 لأي شيء آخر)، تكتب أعمدة disposition **اللي تحميها insert_lead من
الاستبدال** (db.py: LEAD_COLUMNS + human_owned exclusion)، تسجل في
**audit_logs** بـactor/action/payload، وتبعت حدث `lead.*` على الـoutbox.
RESEARCH_MORE ينشئ مهمة ابن (`parent_job_id` + نفس الموضوع → الحقائق
المخزنة بتاعته مستمرة تلقائيًا لأنها subject-keyed).

**إعادة التأهيل** — `lead_requalify` (review_api.py:163): تغيير الـICP
يعيد التقييم من الحقائق المخزنة — **صفر discovery، صفر استهلاك بحث**
(مثبت باختبار: usage_ledger وresearch_facts ثابتين قبل/بعد).

**الحظر الصارم**: مفيش أي أداة أو endpoint إرسال —
`TOOLS` (tools.py:252) فيها 8 أدوات قراءة/حفظ/تحقق فقط، والقرارات البشرية
مش معرفة كأدوات أصلًا (مثبت باختبار test_no_send_or_human_decision_tools_exist).

## 7) البنية التحتية المعاد استخدامها (صفر هدم)

- **آلة الحالة** (jobs.py:46 TRANSITIONS): أُضيفت فروع البحث (المراحل
  الأربع تتبادل + WAITING_FOR_USER + READY_FOR_REVIEW؛ COMPLETED مقصود
  مش خروج مباشر من مرحلة — بوابة المراجعة إلزامية).
- **الطابور** (queue.py): `lease_next` (SKIP LOCKED) :25، `reclaim_expired`
  :52، و`release` :67 الجديدة — تماديةل READY_FOR_REVIEW ما يعلّمش
  COMPLETED (المالك هو البوابة البشرية).
- **Model Gateway** (router.py) زي ما هو: حصص/RPM/tدوير مفاتيح/cooldown،
  و`prefer_provider` للـplanner (لا هبوط صامت: فشل النموذج المثبت = PAUSED
  WAITING_FOR_CAPACITY — orchestrator.py:96 run).
- **Events/Outbox**: قراراتك وأحداث المهام على نفس العمود الفقري idempotent.
- **الـpipeline القديم** شغال كما هو كمسار deterministic/benchmark.

## 8) قاعدة البيانات (4 migrations مطبقة على Supabase الحية)

1. `20260913000001_truth_layer.sql`: research_facts (فهرس فريد
   coalesce-org+subject+field+value)، fact_sources، fact_conflicts،
   open_questions، visited_sources، icp_versions + أعمدة disposition على
   engine.leads + RLS.
2. `20260913000002_truth_rls_tighten.sql`: WITH CHECK بلا NULL-org escape
   (fail-closed) + فهرس فريد لـicp_versions.
3. `20260913000003_research_jobs.sql`: research_context + RLS.
4. `20260913000004_research_context_run.sql`: run_id.
   وSQLite (التطوير): auto-migrations في db.py (`_migrate_lead_disposition_columns`,
   `_migrate_research_context_columns`) — أثبتت نفسها على قاعدة بيانات
   حقيقية قديمة أثناء التشغيل الحقيقي.

## 9) الأمان والعزل

- **ميدل وير** (api/app.py:80): كل `/api/*` محمي — Supabase JWT (JWKS) أو
  توكن MCP الثابت أو كوكي dev — وضع closed = 401 للكل (fail-closed).
- **عزل المستأجرين 4 طبقات**: JWT→membership→حقن organization_id
  (db_pg.py ORG_TABLES/regex) → FORCE RLS بـapp.current_org. **متتحقق
  سلوكيًا على الإنتاج**: صف org-A غير مرئي لـorg-B ولا بدون سياق، تحديث
  عابر مستحيل، كتابة بلا سياق مرفوضة (42501).
- **فصل الثقة**: مفاتيح OpenManus على جهازه؛ الاختبارات محمية من المفاتيح
  الحقيقية بحرمانها في conftest (بما إن load_env بيعيد التحميل، القيم
  تُفرَّغ بـ"" مش delenv — فخ اتحكم وصحيح).
- **القرار البشري غير قابل للاستدعاء من أي نموذج**: القرارات endpoints
  مصادقة فقط، ومش مسجلة كأدوات.

## 10) الاختبارات والتحقق الحقيقي

- **246 passed + 2 skipped** عبر 24 ملف (test_truth: 29، test_integrations: 26،
  test_research_job: 14، test_stage3_review: 10، test_research_orchestrator: 9،
  test_research_api: 9، test_openmanus: 9، test_e2e_research: سيناريو كامل...).
- **E2E** (test_e2e_research.py): شات → job → بحث → حفظ بمصادر → تحقق →
  تأهيل → تماديةل → عرض → القرارات → RESEARCH_MORE → requalify → audit.
- **تشغيلان حقيقيان** (مفاتيح Gemini+Tavily فعلية):
  1. job حقيقي → 4 leads وصلت البوابة + APPROVE_CONTACT مدقق — كشف وأصلح
     3 فجوات (قائمة الأدوات في البرومبت، حلقة الملاحظات، إقفال budget).
  2. التدفق الكامل بمعايير مستخدم: **24 حقيقة بمصادرها (أرقام جدة فعلية)،
     تعارض اسم اتكشف تلقائيًا، 10 leads بعد بوابة الأدلة، قرار مدقق**.

## 11) المعمارية التفاعلية (سطر سطر)

```
شات (start_research / define_icp) أو POST /api/v1/research
  └ ResearchJobManager.create (manager.py:58) → jobs QUEUED + research_context
     └ ResearchOrchestrator.run (orchestrator.py:96)
        ├ _make_plan (:378) — LLM planning (pinned provider)
        ├ _loop (:116): budget_check → _agent_turn (:165)
        │    └ execute_tool (tools.py:317) — scopes + budgets + steps
        │         ├ search_companies (:70) → Tavily حقيقي → استخراج تلقائي → record_fact (truth.py:118)
        │         ├ research_company (:136) → OpenManus (لو مهيأ)
        │         ├ save_fact / verify_fact / list_facts / qualify_lead / ask_user
        ├ _finalize (:229): _verify_emails → _qualify_all → _materialize_leads
        └ ready_for_review → READY_FOR_REVIEW
لوحة المراجعة (GET /api/v1/review/pending → ReviewPanel.tsx)
  └ lead_decision (review_api.py:106) → disposition + audit_logs + حدث
     └ APPROVE_CONTACT = آخر خطوة في النظام (لا يوجد outbound)
```

## 12) ما لم يُبنَ (بقرار) والقيود الصادقة

1. **مرحلة التواصل**: خارج النطاق الحالي بقرارك — APPROVE_CONTACT terminal.
2. **OpenManus الحي**: العقد/العميل/الـwrapper جاهزين ومختبرين وحدات؛
   الربط الحي لما تشغّل الـwrapper عندك (wrapper/README.md).
3. **endpoint حل تعارض بشري مباشر**: `resolve_conflict` داخلي، التعارضات
   معروضة والمسار عليها RESEARCH_MORE — endpoint مخصص مستقبلي.
4. **سرد الشات**: polling كل 5 ثوانٍ (لا SSE).
5. **النشر على Vercel**: يدوي من عندك؛ CI يبني الفرونت تلقائيًا.
