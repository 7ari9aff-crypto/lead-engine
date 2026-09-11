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
| Lead Engine (pipeline كامل) | ✅ | ✅ **جاهز ومختبر (50+ توستس)** |
| Provider Router (quotas/rotation/fallback) | ✅ | ✅ |
| Auth | ✅ JWT/RBAC | ⚠️ كلمة سر واحدة (يُستبدل في المرحلة 1) |
| Database | ✅ Postgres/Supabase + RLS | ⚠️ SQLite تشغيلي + Supabase مزامنة (يتحول في المرحلة 1) |
| Tenancy | ✅ | ❌ (تُبنى في المرحلة 1) |
| Jobs/Workers/Queue | ✅ | ❌ تشغيل متزامن داخل العملية (مرحلة 2) |
| Events/Outbox | ✅ | ❌ (مرحلة 2) |
| Billing/Entitlements | ✅ | ❌ (مرحلة 2) |
| Backup/DR | ✅ PITR + RPO/RTO | ❌ (مرحلة 1 — تفعيل واختبار) |
| Security Engineering | ✅ controls | ⚠️ جزئي (CI scanning في المرحلة 1) |
| API Lifecycle | ✅ /api/v1 | ⚠️ aliases فقط (البادئة في المرحلة 1) |
| Frontend | ✅ Next.js مُؤجل بشروط | ✅ React 19 + Vite SPA (redesign حديث) |

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
