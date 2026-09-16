# Lead Engine — Platform Architecture (Frozen Baseline)

> اعتمدت بتاريخ 2026-09-11. المرجع النهائي للمبادئ والمراحل. أي تعديل على هذه الوثيقة يتطلب قرارًا صريحًا.
> تمييز إلزامي في كل نقاش: **مصمَّم** (على الورق) ≠ **منفَّذ** (في الكود).

## 1) المبادئ المعتمدة (من المعمارية النهائية)

1. **Control Plane / Data Plane**: إدارة المستأجرين والصلاحيات والفوترة منفصلة عن تشغيل الـworkloads.
2. **Lead Engine = Domain Core نقي**: لا يعرف FastAPI ولا Redis ولا JWT — يستقبل Execution Context ويخرج Results وEvents وUsage Signals.
3. **Hybrid Tenant Isolation**: pooled / isolated_compute / dedicated — العزل سلعة تُشترى.
4. **Same Domain, Same Contracts, Same Engine**: الترقية بين مستويات العزل بلا تغيير الـengine أو الـAPI.
5. **Outbox + Idempotent Consumers**: لا محاسبة مزدوجة (event_id فريد في الـledger).
6. **RLS + Application Authorization**: طبقتا حماية لكل صف تجاري.
7. **No framework fashion**: لا microservices ولا Kafka إلا لسبب تشغيلي مُثبت.

## 2) حالات التنفيذ الفعلية (سبتمبر 2026)

| الجانب | مصمَّم | منفَّذ حاليًا |
|---|---|---|
| Lead Engine (pipeline كامل) | ✅ | ✅ **منفَّذ ومختبر (259 اختباراً أخضر 100%)** |
| Provider Router (quotas/rotation/fallback) | ✅ | ✅ |
| Auth | ✅ JWT/RBAC | ✅ Supabase JWT + RBAC فعّال (المسار القديم مُغلق في وضع supabase) |
| Database | ✅ Postgres/Supabase + RLS | ✅ Postgres/Supabase أساسي + RLS + schema `engine` منفصلة (SQLite للـdev/tests فقط) |
| Tenancy | ✅ | ✅ مطبقة (organization_id على كافة الجداول التشغيلية، ORG_TABLES + حقن تلقائي) |
| Jobs/Workers/Queue | ✅ | ✅ SKIP LOCKED، lease، reclaim، backoff (Postgres قوائم انتظار كاملة) |
| Events/Outbox | ✅ | ✅ transactional outbox + idempotent consumers + DLQ + webhooks HMAC |
| Billing/Entitlements | ✅ | ⚠️ Entitlements يومية منفَّذة — Stripe/Subscription غير منفَّذ بعد |
| Backup/DR | ✅ PITR + RPO/RTO | ⚠️ runbook موثق، تجربة استعادة حقيقية متبقية |
| Security Engineering | ✅ controls | ✅ CI حازم (بلا || true)، vercel.json بلا أسرار، pip-audit + pnpm audit |
| API Lifecycle | ✅ /api/v1 | ✅ /api/v1 للمسارات الجديدة + aliases القديمة محفوظة |

## 3) المراحل المعتمدة وDefinition of Done

### المرحلة 0 — إثبات المنتج (قيد الإغلاق)
- [x] إعادة تصميم الواجهة كاملة (ثيم محايد، شات بمُنتقيات، مفاتيح مدموجة)
- [x] إصلاح كراش صفحة المهام (cache collision بين SPA وAPI)
- [x] بناء نهائي + توستس خضراء
- [x] حفظ الشغل على git + تثبيت هذه الوثيقة
- [ ] أول تشغيل حقيقي (benchmark) بأرقام V0 — **بوابة المرحلة**

### المرحلة 1 — أساس الـTenancy (الأساس الذي لن يُغيَّر في الإنتاج)
- [ ] **Supabase Postgres = قاعدة أساسية وحيدة** (SQLite تبقى للـdev/الاختبارات فقط)
- [ ] **Platform core**: organizations + organization_members + api_keys (hashed) + organization_provider_credentials (مشفرة) + audit_logs — كلها بـRLS
- [ ] **Engine schema** منفصل (`engine`) لجداول التشغيل الداخلية، محجوب عن anon/authenticated
- [ ] organization_id على كل جدول تجاري + فهارس tenant-aware
- [ ] Supabase Auth JWT في FastAPI + Tenant Context middleware
- [ ] مفاتيح المزودين مشفرة بـscope لكل مؤسسة
- [ ] **Ops**: PITR مفعّل + تجربة استعادة واحدة ناجحة + RPO=5min / RTO=1h موثقة + dependency scanning في CI
- [ ] بادئة `/api/v1` للمسارات الجديدة + الحفاظ على الـaliases القديمة
- **DoD**: توستس خضراء على SQLite + دخول JWT حقيقي + استعلام tenant-scoped يعمل + advisors نظيفة

### المرحلة 2 — أول عميل مدفوع
**طبقات Outreach المسجلة (تُبنى مع أول قناة outbound أو أول CRM sync — لا قبلها):**
- **Policy / Suppression / Risk gate**: بوابة pre-send موحدة قبل أي outbound action
  (email/WhatsApp/SMS) — suppression list (unsubscribed/bounced/compliant-blocked)،
  قواعد القناة، حدود الحجم، وrisk throttles. النواة موجودة في الدومين بالفعل:
  Legal Gate للتخزين، تحقق الإيميل 5-حالات كمضاد bounce، وquotas الروتر كأول
  risk throttle. المحفز: أول مسار إرسال حقيقي.
- **Integration Platform (OAuth)**: OAuth 2.0 code flow بحالة state موثقة،
  تطبيق واحد لكل مزود يخدم كل العملاء، connection store per-tenant (امتداد
  لـorganization_provider_credentials بحقول access/refresh/expires_at)،
  token refresh في الـworker عبر credential_ref فقط، وadapters بـcapability
  registry — LinkedIn تبقى unavailable رسميًا لحين وصول API معتمد.
  المحفز: أول مزود يحتاج تصريح المستخدم (Gmail send / HubSpot sync).
- Queue + Job Workers منفصلة (leases/heartbeats) + Outbox + Consumers idempotent
- Billing (Subscription + Entitlement + Usage Ledger) + Webhooks موقعة HMAC + Notifications
- Retention/Deletion كـendpoints + SLO أولية + alerting
- **DoD**: عميل يدفع، job يعبر الـqueue كاملًا، webhook يستلم حدثًا موقعًا

### المرحلة 3 — Enterprise
- مستويات العزل الثلاثة فعلًا (Runtime Registry + Provisioning State Machine)
- Kubernetes + Terraform + DR region + SOC 2 evidence
- **DoD**: تينانت dedicated provisioned آليًا من الـstate machine

## 4) قرارات تقنية مُثبتة

| القرار | الاختيار | ملاحظة |
|---|---|---|
| Primary DB | Supabase Postgres (project `lead` / abshiqxxsvdtbdngycpb) | SQLite للـdev فقط |
| Auth | Supabase Auth (JWT) | كلمة السر تُلغى بعد التبديل |
| Driver | psycopg (v3) | مع حافظ ?→%s موثق ومختبر |
| Engine schema | `engine` منفصل | service-role فقط، REVOKE من anon/authenticated |
| التشفير | pgcrypto AES-GCM كمرحلة 1، KMS/envelope لاحقًا | المفاتيح لا تُخزن نصًا أبدًا |
| Frontend | React 19 + Vite (الحالي) | Next.js مُؤجل بشرط: صفحات SEO عامة مدموجة، أو جلسات SSR، أو فريق كبر |
| API | FastAPI + /api/v1 للجديد | aliases القديمة محفوظة لـn8n |
| i18n | البنية جاهزة (logical properties) | الترجمة الفعلية عند دخول سوق جديد |

## 5) قرارات مؤجلة (باسم واضح — ليست مرفوضة)

- Microservices / Kafka / Redis multi-instance: عند ضغط مثبت.
- CQRS read models: عند ثقل استعلامات التحليلات.
- MFA/SSO/SCIM: مع أول عقد enterprise.
- Object storage pipelines: عند ملفات كبيرة حقيقية.
- SOC 2 evidence: المرحلة 3.

## 6) حالة التنفيذ الفعلية (تحديث 2026-09-12)

الوثيقة القديمة كانت متأخرة عن الكود. الجدول ده هو المصدر المُحدَّث:

| الطبقة | الحالة |
|---|---|
| Engine pipeline كامل | منفَّذ ومختبر (تشغيل حقيقي: 84 عميل، 32 مقبول) |
| Provider Router | منفَّذ (أولويات، حصص، RPM، تدوير مفاتيح، cooldown، fallback) |
| Queue على Postgres | منفَّذة (SKIP LOCKED، lease، reclaim، backoff) — tests/test_queue_pg.py |
| Outbox + Events | منفَّذ (outbox، استهلاك idempotent، DLQ بعد 5 محاولات) |
| Webhooks | منفَّذة (HMAC موقعة، delivery log، 3 محاولات لكل جولة) |
| Multi-tenancy | منفَّذة (organizations، members، RLS، org injection) |
| Tenant context لكل request | منفَّذ (JWT → membership → DB handle) — env bridge احتياطي للـworker |
| Auth | Supabase JWT أساسي؛ المسار القديم بكلمة مرور مُغلق في وضع supabase |
| Integrations OAuth | منفَّذة (signed state، توكنات مشفرة، refresh، revoke) — صلبة بإعدادات مزود حقيقية |
| Agents platform | منفَّذة (versions، runs، steps، tools، approvals) |
| MCP | منفَّذ (5 أدوات) — auth/org-scoping للمستأجرين لاحقًا |
| Entitlements | منفَّذة (حدود يومية لكل org) — Billing/Stripe غير منفَّذ |
| Observability / SLO | غير منفَّذ |
| Enterprise isolation | مخطط (provisioning state machine جاهز، dedicated runtime لاحقًا) |

## 7) تصنيف الجداول (Data Isolation Audit — ملزم)

### Tenant-scoped — organization_id إلزامي في الكتابة

jobs · leads · usage_ledger · agent_runs · agent_steps · approvals ·
job_events · evidence · cache · notifications · activity_events · agents ·
research_facts · fact_sources · fact_conflicts · open_questions · visited_sources ·
icp_versions · research_context

- NULL organization_id في agents فقط = وكيل منصة (system agent)
- activity_events القديمة (قبل migration 6) بدون org = صفوف منصة تراثية

### Platform-global — مشتركة للقراءة، لا تحمل بيانات عملاء

providers (تعريفات) · tools (السجل)

### Internal — ليست بيانات مستأجرين

connections (اتصالات مزودين قديمة بنمط الوكلاء؛ حل محلها
public.integration_connections للـOAuth — تُستبعد تدريجيًا)

### قواعد التنفيذ

1. كل INSERT على جدول tenant-scoped يمر عبر ORG_TABLES في db_pg (حقن تلقائي)
2. كل قائمة/قراءة في الـAPI تفلتر: org الحالي + صفوف المنصة (NULL) عند اللزوم
3. لا يجوز endpoint يعرض صفوف tenant آخر بأي شكل

## 8) قرار معماري 2026-09-13 — Agentic Research Target (R0–R6)

قرار صريح بموجب بند "أي تعديل يتطلب قرارًا": اعتماد الهدف النهائي
**Chat-first autonomous research agent** بحد نهائي `APPROVE_CONTACT` —
**بدون أي outbound execution في هذا النظام** (إرسال إيميل/واتساب/لينكدإن
غير موجود وأي أداة من نوع SEND ممنوعة كأدوات وكيل).

- المرجع التنفيذي والملزم: `docs/plan-agentic-research.md` (خريطة المكونات
  Keep/Extend/Refactor، حالات الـresearch job، قواعد Business Truth،
  budgets/stop_reason، الصلاحيات، مراحل R0–R6 وDoD).
- إضافات schema معتمدة: `engine.research_facts`، `engine.fact_sources`،
  `engine.fact_conflicts`، `engine.open_questions`، `engine.visited_sources`،
  `engine.icp_versions`، `engine.research_context` + `leads.disposition` —
  كلها tenant-scoped بـRLS.
- الجدول في القسم 2 يُحدّث: Jobs/Workers/Queue + Events/Outbox + Tenancy
  (منفذة أصلًا) تُوسّع — لا يُستبدل أي منها. طبقة Truth/Verification/
  Qualification تُبنى أعلى الموجود (extension إلزامي، لا بناء موازٍ).
- ICP تنتقل من YAML إلى `engine.icp_versions` (versioned per-org) — YAML
  يظل مصدر import فقط. Company Profile كواجهة منفصلة: مؤجل — الـintent
  يأتي من الشات مباشرة (chat-first).
