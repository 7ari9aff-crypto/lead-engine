# Runbook — Backup / Restore (Lead Engine)

> حالة التحقق: 2026-09-11 — `pitr_enabled: false`, `backups: []` (متأكد عبر
> Management API). **دي أعلى أولوية تشغيلية مفتوحة في المشروع.**

## 1) تفعيل الحماية (مرة واحدة — يحتاج مالك المشروع)

PITR والنسخ اليومية ميزة خطة (Pro فأعلى) ومتاحة من لوحة Supabase فقط، مش من
الـManagement API:

1. Dashboard → مشروع `lead` (abshiqxxsvdtbdngycpb) → **Database → Backups**.
2. لو الخطة Free: ارتقِ لـPro (النسخ اليومية جاهزة فورًا).
3. فعّل **Point-in-Time Recovery** (نفس الصفحة) — الـAPI بيقول حاليًا
   `walg_enabled: true` فالبنية التحتية جاهزة، ناقص التفعيل.
4. اختياري للـDR: **Cross-region replication** من إعدادات الـbackups.

بعد التفعيل تحقق:
```bash
curl -s -H "Authorization: Bearer $SUPABASE_ACCESS_TOKEN" \
  https://api.supabase.com/v1/projects/abshiqxxsvdtbdngycpb/database/backups
# المتوقع: pitr_enabled: true + قائمة backups غير فاضية
```

## 2) الأهداف (من docs/architecture.md §6)

```text
RPO = 15 دقيقة  (PITR granularity)
RTO = ساعة واحدة للاستعادة الكاملة
Retention = حسب الخطة (7 أيام PITR افتراضيًا)
```

## 3) إجراء الاستعادة الكاملة (Full restore)

1. Dashboard → Database → Backups → اختر نقطة زمنية (PITR) أو نسخة يومية.
2. **Restore ينشئ قاعدة جديدة** — المشروع نفسه لا يتراجع للخلف.
3. حدّث `SUPABASE_DB_URL` في بيئة التشغيل (Vercel + worker) لتشير للقاعدة
   المستعادة، ثم redeploy/restart.

## 4) استعادة مستأجر واحد (tenant-level)

مع hybrid isolation:
- **POOLED**: restore لقاعدة ظل (restore to new project) → استخراج صفوف
  `organization_id = X` من كل الجداول → إعادة إدراجها في الأساسية. إجراء
  يدوي موثق — لا تلمس قاعدة الإنتاج.
- **DEDICATED** (مرحلة 3): استعادة القاعدة المخصصة كاملة — بسيطة.

## 5) تجربة الاستعادة (Restore drill) — شرط إغلاق المرحلة 1

- [ ] بعد تفعيل PITR: اعمل restore لنقطة عمرها ساعة إلى مشروع اختبار.
- [ ] تحقق: عدد صفوف `engine.jobs` و`public.organizations` مطابق للأصل.
- [ ] سجل التاريخ والمدة هنا (RTO المقاس مقابل الهدف).

```text
Drill #1: [تاريخ] — [المدة] — [النتيجة]
```

## 6) ما لا تغطيه النسخ

- مفاتيح `.env` المحلية (المفاتيح مشفرة في القاعدة — النسخة تغطيها).
- إعدادات Vercel/env في المنصات الخارجية — وثّقها يدويًا في مكان آمن.
