# OpenManus Wrapper — التشغيل على الجهاز التاني

الخدمة دي هي الجسر بين Lead Engine وOpenManus. العقد الكامل موثق في
[`docs/openmanus-contract.md`](../docs/openmanus-contract.md).

## المتغيرات المطلوبة على جهاز OpenManus

| المتغير | المعنى |
|---|---|
| `OPENMANUS_CWD` | المسار الكامل لمجلد OpenManus (اللي فيه `run_flow.py`) |
| `OPENMANUS_ENTRY` | `run_flow.py` (متعدد الوكلاء — الافتراضي) أو `main.py` |
| `OPENMANUS_PYTHON` | بايثون البيئة اللي فيها OpenManus (افتراضي `python`) |
| `OPENMANUS_WRAPPER_TOKEN` | سر مشترك — نفس قيمة `OPENMANUS_TOKEN` عند Lead Engine |
| `OPENMANUS_TASKS_DIR` | اختياري — مجلد حفظ حالة المهام |

## تشغيل

```bash
pip install -r requirements.txt
export OPENMANUS_CWD=$HOME/OpenManus
export OPENMANUS_WRAPPER_TOKEN=$(openssl rand -hex 24)
uvicorn openmanus_wrapper:app --host 0.0.0.0 --port 8600
```

مفاتيح الـLLM بتاعة OpenManus تتظبط في `config/config.toml` بتاعه هو —
الـwrapper ما بيشوفهاش أبدًا.

## فضحه لجهاز Lead Engine

- **Tailscale** (الأسهل والأأمن): `tailscale serve 8600` — هيديك HTTPS داخلي.
- **ngrok**: `ngrok http 8600`.
- **VPS**: وراء nginx + TLS.

وبعدين على جهاز Lead Engine في `.env`:

```bash
OPENMANUS_BASE_URL=https://<العنوان>
OPENMANUS_TOKEN=<نفس OPENMANUS_WRAPPER_TOKEN>
```

## اختبار

```bash
curl -s localhost:8600/health
curl -s -X POST localhost:8600/tasks -H "Authorization: Bearer $OPENMANUS_WRAPPER_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"type":"browse","url":"https://example.com","objective":"extract contact info","timeout_seconds":120}'
curl -s localhost:8600/tasks/<task_id> -H "Authorization: Bearer $OPENMANUS_WRAPPER_TOKEN"
```
