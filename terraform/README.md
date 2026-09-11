# Terraform (Phase 3 — skeleton)

المصدر الحقيقي للبنية النهائية في المرحلة 3. الملفات هنا skeleton مقصود:
البنية الحالية Vercel + Supabase وتُدار من لوحاتها. عند أول عميل
isolated/dedicated يُفعَّل هذا المسار فعليًا.

المخطط (من docs/architecture.md §26):
- network: VPC + LB + WAF attachment
- kubernetes: cluster + node pools (shared / tenant-isolated / dedicated)
- databases: dedicated Postgres/Redis لعملاء dedicated فقط
- secrets: KMS root key + tenant KEKs
- observability: OTel collector + alerting
