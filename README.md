# Lead Engine

محرّك توليد leads واعي بالـquotas، مبني على تقسيم ثلاثي:

- **n8n** = الـorchestration والجدولة (يستدعي الـengine يوميًا)
- **FastAPI** = الـengine نفسه (الـrouter، الـproviders، الـpipeline)
- **Supabase** = قاعدة بيانات الـleads (companies / contacts / claims / leads)

```
n8n (Schedule 06:00)
   │  POST /benchmark/run
   ▼
FastAPI — Lead Engine
   │
   ├── Provider Router ──► Search: Tavily → Brave → Exa
   │                    └► LLM: Gemini → Groq → OpenRouter → Ollama (local)
   │                    └► Data: Apollo (search=0 credit)
   │                    └► Email: Hunter → Abstract → Local SMTP
   │
   ├── Pipeline: discovery → normalize → dedup → hard filter
   │             → qualification → enrichment → verification
   │             → scoring → legal gate
   │
   └── POST /sync-supabase ──► Supabase lead database
```

## المبادئ المصممة في الكود

| القرار | التنفيذ |
|---|---|
| Quota exhaustion ≠ failure | الجوب بيتحوّل `PAUSED` بـ`pause_reason` و`resume_at`، مش `FAILED` |
| Job state machine | QUEUED → RUNNING → (DEGRADED) → COMPLETED / PAUSED → RESUMING |
| Provider Registry | جدول في قاعدة البيانات بأولويات وquotas — مش if/else |
| Router decisions | quota + rate limit + headers (`x-ratelimit-remaining`) + health |
| Local LLM fallback | Ollama آخر سلسلة، والمهام المسموحة له محددة، والناتج `processing_mode: degraded_local` |
| 3-level cache | L1 request / L2 entity / L3 evidence — TTLs من `config/cache_policy.yaml` |
| Email verification | syntax → MX → disposable → role → provider → SMTP + catch-all probe، والنتيجة 5 حالات: `DELIVERABLE / RISKY / CATCH_ALL / INVALID / UNKNOWN` — الـcatch-all **مش** valid |
| Dedup | exact (domain/email/phone/linkedin) → identity (name+city+country) → fuzzy (>0.95 merge، 0.85–0.95 review، والأسماء المتشابهة بدومينات مختلفة **عمرها** ما تندمج تلقائيًا) |
| Legal Gate | policy engine من `config/legal_policies/` (SA policy موجاه لنظام PDPL) — default-deny، مش legal advice |
| Selective enrichment | Apollo search = 0 credits، الـenrichment (1–9 credits/شخص) محسوب بـbudget صريح |

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env          # حتّ المفاتيح (أي مفتاح ناقص = الـprovider يتصفّي تلقائيًا)

python3 -m lead_engine init
python3 -m lead_engine benchmark --dry-run    # end-to-end على fixtures بدون شبكة
python3 -m lead_engine providers              # حالة الـregistry والاستهلاك
python3 -m lead_engine benchmark              # تشغيل حقيقي (محتاج مفاتيح في .env)
```

### الـAPI

```bash
python3 -m lead_engine serve --port 8000
```

| Endpoint | الوظيفة |
|---|---|
| `GET /health` | فحص سريع |
| `GET /providers` | حالة الـregistry + الاستهلاك |
| `POST /benchmark/run` `{icp, dry_run}` | تشغيل الـV0 pipeline كامل |
| `GET /jobs/{id}` / `POST /jobs/{id}/resume` | حالة الجوب / استئناف PAUSED |
| `GET /leads?job_id=&stage=ACCEPTED` | الـleads النهائية |
| `POST /verify-email` `{email}` | التحقق 5-حالات |
| `GET /report/{job_id}` | تقرير الـbenchmark |
| `POST /sync-supabase` `{job_id}` | دفع الـleads لقاعدة Supabase |

## الـV0 Benchmark

الهدف: إثبات إن الـfree stack يعطي 20–30 lead حقيقيين قبل بناء أي حاجة أكبر.
الـICP: عيادات أسنان سعودية (جدة/الرياض) بـ3+ فروع ونشاط تسويقي — `config/icp/v0_saudi_dental.yaml`.

المقاييس المحسوبة تلقائيًا في `outputs/report.md`:
discovery candidates، duplicate rate، qualification scored، enrichment success،
contact coverage، email validity، **quota units per lead**، total cost (هدف V0: $0).

ملاحظة تغطية: أخطر افتراض في V0 هو إن مصادر الـAPIs تغطي العيادات السعودية الصغيرة
(كتير منها بدون دومين، شغّالة واتساب/انستجرام). لو النتايج ناقصة، المسار البديل:

```bash
python3 -m lead_engine benchmark --seed my_seed_list.csv
```
(أعمدة: `name, domain, city, email, phone, website, notes` — collected يدويًا)

## Supabase

الـschema الحي في مشروع `lead` موثّق في `supabase/schema.sql` (متولّد من قاعدة
البيانات نفسها). الـmapping:

| Engine | Supabase |
|---|---|
| ICP + job | `campaigns` + `icp_profiles` |
| job state | `jobs.status` |
| usage_ledger | `job_resource_usage` |
| deduped lead | `companies` (+`company_claims`, `company_observations`) |
| decision maker | `company_contacts` |
| email_status | `contact_verifications` |
| stage / legal | `leads.status` / `leads.legal_status` |

المطلوب في `.env`: `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` (service role).

## n8n

الـworkflow: `n8n/lead_engine_benchmark_scheduler.ts` (ومنشور فعلًا على
الإنستنس: workflow `eqW6MZWrnZ9K2H84`) — يوميًا 06:00:
Run benchmark → IF COMPLETED → Sync to Supabase → Get Report.

خطوات التفعيل:
1. انشر الـFastAPI على URL عام (مثلًا Railway) — n8n السحابي مش بشوف `localhost`.
2. عدّل `engineBaseUrl` في node "Config".
3. فعّل الـworkflow.

## Tests

```bash
python3 -m pytest tests/ -q     # 31 test: dedup, verification, cache, router failover, state machine, legal gate
```

## أمان

- أي مفتاح بيتحمّل من `.env` فقط — `.env` مستثنى من git.
- التوكنات اللي اتبعتت في الشات تعتبر معرّضة: بدّلها (GitHub PAT، n8n MCP bearer،
  Supabase sbp_ token) بعد الانتهاء، واستخدم fine-grained tokens بأقل صلاحية.
