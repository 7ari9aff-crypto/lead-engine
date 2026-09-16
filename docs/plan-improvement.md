# خطة التحسين الشاملة — Lead Engine

> كُتبت 2026-09-16 بناءً على فحص الكود الفعلي: `main @ c66f8f4`، شجرة نظيفة،
> **259 اختبار أخضر + 2 متخطى** (تشغيل فعلي 48.85s)، لا فاشل.
> القاعدة الملزمة من `architecture.md`: **مصمَّم ≠ منفَّذ** — كل بند هنا
> مربوط بدليل في الكود أو بغياب موثق. لا يُعدّل بند دون قرار صريح.

## 1) نقطة البداية — ما هو متحقق منه فعليًا

| المسار | الحالة | الدليل |
|---|---|---|
| Pipeline + Router + Truth + Research (R0–R6) | منفَّذ ومختبر | 259 اختبار، `docs/report-implementation.md` |
| Multi-tenancy + RLS + JWT | منفَّذ ومتحقق سلوكيًا | `db_pg.py` ORG_TABLES، migrations 6–8 |
| Queue/Outbox/Webhooks | منفَّذ | `queue.py` SKIP LOCKED، `events.py` |
| CI | يعمل | `.github/workflows/ci.yml` + `sync-frontend.yml` |
| النشر | Vercel serverless، inline execution + drain endpoint | commit `c66f8f4`، `vercel.json` maxDuration=60 |
| Observability / SLO | **غير منفَّذ** | `architecture.md` §6 |
| Billing/Stripe | **غير منفَّذ** | `architecture.md` §6 (entitlements فقط) |
| Backup/DR (PITR + تجربة استعادة) | runbook فقط | `docs/runbook-restore.md` بلا تجربة موثقة |
| أول benchmark حقيقي (بوابة المرحلة 0) | **مفتوح** | `architecture.md` §3 — البند الوحيد المتبقي |
| OpenManus الحي | وحدات مختبرة، الربط الحي متبقٍّ | `report-implementation.md` §12 |

## 2) فجوات مقاسة من الفحص

1. **مفاتيح المزودين ناقصة**: الفعّالة في `.env` = TAVILY + EXA + GEMINI + Supabase
   + OpenManus فقط. الفارغة/المعلّقة: BRAVE، GROQ، OPENROUTER، APOLLO، HUNTER،
   ABSTRACT، N8N — سلاسل الـfallback مقطوعة عند أول حلقة، ولا email verification
   خارجي، ولا enrichment بـApollo.
2. **توكنات معرّضة**: README §أمان يوثق أن GitHub PAT وn8n bearer وsbp_ انكشفوا
   في شاتات — التدوير واجب ولم يُوثق إتمامه.
3. **CI غير حازم**: `pip-audit ... || true` (ci.yml) = الفحص الأمني لا يوقف شيئًا؛
   لا secret scanning، لا فحص أمني للفرونت.
4. **سقف serverless**: maxDuration=60s والمهام الطويلة (research minutes-long)
   تعتمد على drain endpoint — حل مؤقت بلا مراقبة ولا ضمان إتمام.
5. **سرد الشات**: SSE بدأ جزئيًا (live research chip، commit `2e684fc`) والباقي
   polling كل 5s (موثق §12 في تقرير التنفيذ).
6. **وثيقة architecture.md §2 متأخرة**: تقول "50 اختبار / كلمة سر واحدة / SQLite
   تشغيلي" — الواقع 259 اختبار + Supabase JWT + Postgres multi-tenant (§6 أحدث).
7. ~~**resolve_conflict داخلي فقط**~~ — **مُصحَّح**: التعارضات معروضة ومحلولة عبر API:`GET /api/v1/conflicts` و `POST /api/v1/conflicts/{id}/resolve` ومربوطة بصفحة المراجعة `Review.tsx` (9 اختبارات تغطيها في `test_stage3_review.py`). هذه الفجوة **مغلقة**.


## 3) محاور التنفيذ (بالأولوية)

### T0 — أمان فوري (الأسبوع الحالي، شبه بلا كود)

| # | البند | DoD |
|---|---|---|
| 1 | تدوير كل التوكنات المعرّضة: GitHub PAT، n8n MCP bearer، Supabase sbp_ | توكنات جديدة fine-grained بأقل صلاحية، القديمة ملغاة، `.env` المحلي وVercel env محدّثان، الإتمام موثق بتاريخه |
| 2 | إخراج `VITE_SUPABASE_*` من `web/vercel.json` إلى Vercel env vars | الريبو بلا أي قيم حتى العامة القابلة للتدوير |
| 3 | تدقيق تاريخي: `git log --all -- .env` | إثبات أن `.env` لم يُرفع أبدًا — ولو وُجد أثر: تدوير فوري لكل قيمة فيه |
| 4 | CI حازم: إزالة `|| true` من pip-audit + إضافة gitleaks + `pnpm audit` للفرونت | أي ثغرة high/critical أو سرّ مسرّب = build أحمر |

### T1 — إغلاق بوابة المرحلة 0: أول benchmark حقيقي

البند الوحيد المفتوح في المرحلة 0 (`architecture.md` §3).

1. **قرار المفاتيح قبل التشغيل**: إما إكمال BRAVE + GROQ + HUNTER كحد أدنى
   (كلها free tier)، أو قرار صريح موثق بالتشغيل بالمتاح (TAVILY/EXA/GEMINI)
   مع قبول خفوت التغطية وسلاسل fallback المقطوعة.
2. التشغيل: `python -m lead_engine benchmark` بـICP `v0_saudi_dental`.
3. المقاييس التلقائية في `outputs/report.md`: discovery candidates، duplicate
   rate، email validity، **quota units per lead**، total cost (هدف V0: $0).
4. تقييم خطر التغطية الموثق في README (عيادات صغيرة بدون دومين، واتساب/انستجرام)
   — لو النتائج ناقصة: المسار البديل `--seed` بقائمة يدوية جاهز أصلًا.
- **DoD**: `outputs/report.md` بأرقام حقيقية + قرار GO/NO-GO موثق هنا.

### T2 — OpenManus الحي (إتمام R4)

- العقد/العميل/wrapper جاهزون ومختبرون (9 اختبارات) ومفاتيحه مضبوطة في `.env`.
- الخطوات: تشغيل `wrapper/openmanus_wrapper.py` على الجهاز الثاني → research job
  حقيقي → التحقق أن `research_company` حوّل النتائج إلى facts بمصادرها.
- **DoD**: job موثق فيه facts مصدرها browsing حقيقي (fact_sources + visited_sources
  ممتلئة)، وسقوط الـruntime يظهر UNKNOWN بصدق لا كسر.

### T3 — Observability / SLO (الفجوة المعمارية الوحيدة المفتوحة كليًا)

1. **Telemetry منظّم لكل job**: duration، tool_calls، model_calls، searches،
   tokens/cost، stop_reason — loguru موجود في requirements، يُعتمد معيارًا واحدًا
   بحقول JSON ثابتة بدل print المبعثرة.
2. **لوحة صحة تشغيلية**: usage per provider، معدل نجاح المهام، عمق الـqueue،
   زمن الاستجابة — تتغذى من usage_ledger + job_events الموجودين (لا بنية موازية).
3. **SLO معلن**: توفر `/health`، معدل نجاح المهام، p95 للبحث — وتنبيه عند الكسر.
- **DoD**: أي job يُنتج سجل telemetry كامل قابل للاستعلام + Overview تعرضه.

### T4 — إتمام أساس المنصة (بقايا المرحلة 1)

1. **PITR + تجربة استعادة**: تفعيل PITR على Supabase، تنفيذ `runbook-restore.md`
   فعليًا مرة كاملة، توثيق RPO/RTO **المقاسَين** لا المفترضين.
2. **جرد `/api/v1` آلي**: كل مسار جديد تحت البادئة والـaliases القديمة محفوظة
   (invariant) — سكربت يعدّد routes ويطابق القاعدة ويُدرج في CI.
3. **توحيد قاعدة الإنتاج**: Postgres هو الأساسي الوحيد في الإنتاج؛ SQLite يُحصر
   صراحة في dev/tests (dual-dialect موجود أصلًا في `db_pg.py`/`db.py`).
4. **تحديث `architecture.md` §2** ليطابق الواقع (259 اختبار، JWT، tenancy منفذة).
- **DoD**: تجربة استعادة موثقة + جرد routes نظيف في CI + وثيقة معمارية محدثة.

### T5 — تحجيم التنفيذ (serverless → hybrid)

- **الواقع المقاس**: `vercel.json` maxDuration=60s؛ المهام الطويلة تُنفّذ inline
  + drain endpoint (commit `c66f8f4`) — يصلح للـbenchmark، لا يصلح لـresearch
  متعدد الدقائق مع OpenManus.
- **الخيار المعتمد (أ)**: worker خارجي دائم يشغّل `python -m lead_engine worker`
  ضد نفس Postgres — **الكود جاهز أصلًا** (queue SKIP LOCKED + lease + reclaim +
  `__main__.py worker` + فروع research/benchmark). الاستضافة: Railway/Fly/VPS.
  الـAPI على Vercel يكتفي بالإنشاء والإدراج في الـqueue.
- **الخيار الاحتياطي (ب)**: cron/QStash يستدعي drain endpoint كل دقيقة.
- **DoD**: research job 5+ دقائق يكتمل على الإنتاج بلا تدخل يدوي، والـdrain
  يبقى كشبكة أمان مع مراقبة (من T3).

### T6 — أول عميل مدفوع (المرحلة 2) — بعد T1–T5 فقط

1. **Billing/Stripe**: entitlements موجودة (حدود يومية لكل org) — فوقها:
   خطط، قيود usage، تجاوز مدفوع، webhooks Stripe.
2. **Outreach Safety (لا تُبنى قبل أول قناة إرسال حقيقية — قرار معماري قائم)**:
   Policy/Suppression/Risk gate قبل أي send؛ النواة موجودة (Legal Gate +
   email verification 5-حالات + quotas كـrisk throttle) — الإضافة طبقة
   pre-send موحدة فقط، والـinvariant يبقى: APPROVE_CONTACT terminal.
3. **OAuth Integrations**: صلبة بموجب §6 — تبقى اختبار قبول بمزود حقيقي واحد.
- **DoD**: عميل واحد يعمل بالكامل على multi-tenant حقيقي بفوترة مفهومة.

### T7 — جودة هندسية مستمرة (أفقي عبر كل المحاور)

1. **قياس تغطية**: pytest-cov في CI بحد أدنى معلن (الخط: ≥85% على `truth.py`
   و`orchestrator.py` و`tools.py` و`db_pg.py`).
2. **E2E ليلي**: `test_e2e_research.py` + `test_e2e_live_stack.py` على schedule
   يومي في CI، لا عند الـpush فقط.
3. **سرد الشات كامل SSE**: التعميم على كل أحداث الـorchestrator (بدل polling 5s).
4. **endpoint حل تعارض بشري**: `POST /api/v1/facts/{id}/resolve` بمصادقة + audit
   (المسار الداخلي موجود في `truth.py` — يُعرّض فقط).
5. **توثيق الأدوات**: كل أداة جديدة تُحدّث TOOLS_DOC تلقائيًا (مصدر واحد للحق).
- **DoD**: كلها بنود CI/تجربة، تُقاس آليًا.

## 4) المصفوفة الزمنية والاعتماديات

| المسار | الاعتماد | الجهد التقديري | القيمة |
|---|---|---|---|
| T0 أمان فوري | لا شيء | 2–4 ساعات | إغلاق مخاطر جسيمة |
| T1 benchmark V0 | لا شيء | 1 يوم + قرار مفاتيح | بوابة إغلاق المرحلة 0 |
| T2 OpenManus حي | T0 فقط (توكن جديد) | نصف يوم | عمق تحقق حقيقي |
| T3 Observability | لا شيء | 2–3 أيام | رؤية تشغيلية كاملة |
| T4 أساس المنصة | لا شيء | 1–2 أيام | إغلاق المرحلة 1 رسميًا |
| T5 hybrid worker | T3 للمراقبة | 1 يوم (الكود جاهز) | مهام طويلة بلا سقف 60s |
| T6 عميل مدفوع | T1–T5 مكتملة | أسبوعان | إيراد |
| T7 جودة | مستمر | مدمج | حماية الزخم |

## 5) Invariants (لا تُكسر أبدًا — موروثة من الوثائق المعتمدة)

- **لا outbound إطلاقًا**: APPROVE_CONTACT آخر حد؛ أي أداة من نوع SEND ممنوعة.
- **Extension فوق الموجود** — ممنوع أي نظام موازٍ.
- **259 اختبار تبقى خضراء** + كل مسار جديد يجيب اختباراته.
- **الـaliases القديمة محفوظة** (n8n)؛ الجديد حصرًا تحت `/api/v1`.
- **SQL بـ`?` placeholders**؛ `engine.*` bare؛ `public.*` عبر `_t()`.
- كل جدول تجاري جديد: **organization_id + RLS + ORG_TABLES**.
- **`.env` لا يُرفع أبدًا**؛ النموذج ليس مصدر الحقيقة (facts + provenance).
- كل قرار مهم (decision/conflict/budget stop) في **audit_logs**.

