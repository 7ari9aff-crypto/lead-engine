# OpenManus Integration Contract (R4)

المرجع الملزم للتكامل بين Lead Engine (هذا الريبو) وOpenManus runtime
(خدمة تصفح عميق تعمل على بنية المستخدم — حاليًا جهاز ثانٍ).
Lead Engine بيتكلم مع الـruntime عبر REST فقط — **لا يوجد أي اعتماد على
كود OpenManus داخل هذا الريبو**، ومفاتيح OpenManus تفضل على جهازه.

## الاتجاه والثقة

```
Lead Engine (agent tool: research_company)
    │  HTTPS + Bearer OPENMANUS_TOKEN
    ▼
OpenManus Wrapper (wrapper/openmanus_wrapper.py)  ← يعمل على جهاز المستخدم
    │  subprocess: python run_flow.py  (prompt عبر stdin)
    ▼
OpenManus (مفاتيح LLM خاصة به في config/config.toml)
```

- الـwrapper جزء من هذا الريبو لكنه يُنشر على جهاز OpenManus.
- Lead Engine يعرف الـruntime بمتغيرين فقط (في .env هنا):

```bash
OPENMANUS_BASE_URL=https://<جهاز-المستخدم>/    # ngrok / tailscale / VPS
OPENMANUS_TOKEN=<سر مشترك>
```

لو المتغيرين مش موجودين: أداة `research_company` ترجع `UNAVAILABLE` بصدق،
والوكيل يكمل بمقتطفات البحث — **لا يوجد fallback وهمي** (directive §38).

## Endpoints

### `POST /tasks`
```json
{
  "type": "research" | "browse",
  "objective": "Investigate clinic-c.com: contact info, branches, decision maker",
  "url": "https://clinic-c.com",          // اختياري (browse)
  "max_steps": 15,                        // اختياري
  "timeout_seconds": 240                  // اختياري — سقف كامل للمهمة
}
→ 200 {"task_id": "tsk_...", "status": "queued"}
→ 401 invalid token · 422 bad payload · 503 openmanus not installed
```

### `GET /tasks/{task_id}`
```json
{
  "task_id": "tsk_...",
  "status": "queued" | "running" | "completed" | "failed" | "timeout",
  "error": null,
  "result": {                             // عند completed فقط
    "summary": "سطر واحد يلخص ما وجده",
    "title": "Clinic C — Official Site",
    "url": "https://clinic-c.com",
    "http_status": 200,
    "facts": [
      {"field": "phone", "value": "+966501234567",
       "source_url": "https://clinic-c.com/contact",
       "quote": "call us at ...", "inferred": false}
    ],
    "sources": [{"url": "...", "title": "...", "http_status": 200}]
  }
}
```

### `GET /health`
`{"status": "ok", "openmanus_entry": "run_flow.py", "version": "1.0.0"}`

## قواعد الـfacts اللي يرجعها الـwrapper

1. كل fact لازم يكون له `field` و`value` و`source_url` — المصدر إلزامي.
2. `inferred=true` فقط للاستنتاج الموثق بالسبب في `quote` — بلا مصدر مباشر.
3. ممنوع تخمين أرقام/إيميلات؛ "لم أجد" = الحقل مش موجود في الرد أصلًا.
4. Lead Engine يعامل كل حقيقة قادمة UNVERIFIED ويتحقق بالمصدر الثاني
   أو أدوات التحقق — الثقة تُبنى في Truth Layer مش في الـruntime.

## التنفيذ على جهاز OpenManus

```bash
# 1) OpenManus نفسه (مفاتيحه في config/config.toml — عنده)
git clone https://github.com/FoundationAgents/OpenManus.git
cd OpenManus && uv venv && uv pip install -r requirements.txt
cp config/config.example.toml config/config.toml   # حط مفتاح الـLLM بتاعه

# 2) الـwrapper
pip install -r wrapper/requirements.txt
export OPENMANUS_CWD=/path/to/OpenManus            # مجلد الريبو
export OPENMANUS_ENTRY=run_flow.py                 # أو main.py
export OPENMANUS_WRAPPER_TOKEN=<نفس OPENMANUS_TOKEN>
uvicorn openmanus_wrapper:app --host 0.0.0.0 --port 8600

# 3) فضحه (أي واحدة تكفي): ngrok http 8600 / tailscale / VPS مع HTTPS
```

ثم على جهاز Lead Engine: `OPENMANUS_BASE_URL` + `OPENMANUS_TOKEN` في `.env`.

## اختبار الاتصال بعد الربط

```bash
curl -s $OPENMANUS_BASE_URL/health -H "Authorization: Bearer $OPENMANUS_TOKEN"
curl -s -X POST $OPENMANUS_BASE_URL/tasks -H "Authorization: Bearer $OPENMANUS_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"type":"browse","url":"https://example.com","objective":"extract contact info"}'
```
