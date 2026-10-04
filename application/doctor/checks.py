"""The sentinel checks — one function per failure mode.

Each check returns DoctorCheck with a precise cause + evidence. Registered
in infrastructure/providers/doctor_registry.py (composition), so the
application layer stays framework-free.
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone

from contracts.doctor import CheckStatus, DoctorCheck

PLAINTEXT_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")


def check_db_latency(backend, settings, org) -> DoctorCheck:
    t0 = time.monotonic()
    backend.system_one("SELECT 1")
    ms = round((time.monotonic() - t0) * 1000, 1)
    status = CheckStatus.OK if ms < 500 else CheckStatus.WARN
    return DoctorCheck("db.latency", "اتصال قاعدة البيانات وزمن الاستجابة",
                       status, f"زمن الاستجابة {ms}ms", {"latency_ms": ms})


def check_migrations(backend, settings, org) -> DoctorCheck:
    applied = backend.applied_migrations()
    files = backend.migration_files()
    missing = sorted(set(files) - set(applied))
    drifted = [v for v, chk in files.items() if v in applied and applied[v] != chk]
    if drifted:
        return DoctorCheck("db.migrations", "انزياح المايجريشنز", CheckStatus.FAIL,
                           f"ملفات معدّلة بعد تطبيقها: {drifted} — ممنوع تعديل مايجريشن مطبق",
                           {"drifted": drifted})
    if missing:
        return DoctorCheck("db.migrations", "انزياح المايجريشنز", CheckStatus.FAIL,
                           f"مايجريشنز على القرص غير مطبقة: {missing}",
                           {"missing": missing})
    return DoctorCheck("db.migrations", "انزياح المايجريشنز", CheckStatus.OK,
                       f"{len(applied)} مايجريشن متطبقة ومطابقة")


def check_rls_enforced(backend, settings, org) -> DoctorCheck:
    """Anonymous select on a tenant table MUST return 0 — otherwise RLS is
    absent/bypassed and every tenant is exposed."""
    row = backend.system_one(
        """SELECT (SELECT count(*) FROM company_identity.companies) AS n,
                  (SELECT relforcerowsecurity FROM pg_class
                    WHERE relname = 'companies'
                      AND relnamespace = 'company_identity'::regnamespace) AS forced""")
    if row["forced"] is not True:
        return DoctorCheck("db.rls", "فرض RLS", CheckStatus.FAIL,
                           "FORCE ROW LEVEL SECURITY غير مفعل على companies",
                           row)
    if row["n"] != 0:
        return DoctorCheck("db.rls", "فرض RLS", CheckStatus.FAIL,
                           f"قراءة بدون tenant رجّعت {row['n']} صف — العزل مكسور",
                           row)
    return DoctorCheck("db.rls", "فرض RLS", CheckStatus.OK, "قراءة مجهولة = 0 صف")


def check_app_role(backend, settings, org) -> DoctorCheck:
    row = backend.system_one(
        """SELECT current_user AS u,
                  (SELECT rolsuper FROM pg_roles WHERE rolname = current_user) AS super,
                  (SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user) AS bypass""")
    if row["super"] or row["bypass"]:
        return DoctorCheck("db.app_role", "صلاحيات دور التطبيق", CheckStatus.FAIL,
                           "دور التطبيق superuser أو bypassrls — RLS بيتخطى بالكامل", row)
    return DoctorCheck("db.app_role", "صلاحيات دور التطبيق", CheckStatus.OK,
                       f"{row['u']} — بدون صلاحيات تخطٍ")


def check_queue_starved(backend, settings, org) -> DoctorCheck:
    row = backend.system_one(
        """SELECT count(*) AS n, max(created_at) AS oldest
           FROM runtime.jobs WHERE state = 'QUEUED'""")
    if row["n"] == 0:
        return DoctorCheck("queue.starved", "طابور مهجور", CheckStatus.OK, "لا مهام منتظرة")
    age_min = backend.system_one(
        "SELECT round(extract(epoch FROM (now() - %s)) / 60) AS mins", (row["oldest"],))["mins"]
    if age_min >= 10:
        return DoctorCheck("queue.starved", "طابور مهجور", CheckStatus.FAIL,
                           f"{row['n']} مهمة منتظرة وأقدمها {age_min} دقيقة — لا ووركر حي يسحبها",
                           {"queued": row["n"], "oldest_minutes": age_min})
    return DoctorCheck("queue.starved", "طابور مهجور", CheckStatus.OK,
                       f"{row['n']} في الانتظار — أقدمها {age_min} دقيقة")


def check_stuck_jobs(backend, settings, org) -> DoctorCheck:
    rows = backend.system_all(
        """SELECT id::text, state, lease_expires_at FROM runtime.jobs
           WHERE state IN ('PLANNING','DISCOVERING','RESEARCHING','ENRICHING',
                           'VERIFYING','SCORING','QUALIFYING','CANCELLING')
             AND lease_expires_at < now()""")
    if rows:
        return DoctorCheck("queue.stuck", "مهام عالقة (lease منتهٍ)", CheckStatus.FAIL,
                           f"{len(rows)} مهمة بـ lease منتهي والـ reaper ماغلطش عليها",
                           {"job_ids": [r["id"] for r in rows[:10]]})
    return DoctorCheck("queue.stuck", "مهام عالقة (lease منتهٍ)", CheckStatus.OK, "لا مهام عالقة")


def check_failing_jobs(backend, settings, org) -> DoctorCheck:
    rows = backend.system_all(
        """SELECT id::text, last_error, attempts FROM runtime.jobs
           WHERE state = 'FAILED' AND finished_at > now() - interval '24 hours'
           ORDER BY finished_at DESC LIMIT 5""")
    if rows:
        return DoctorCheck("jobs.failing", "مهام فشلت في 24 ساعة", CheckStatus.WARN,
                           f"{len(rows)} مهمة فشلت — راجع last_error لكل واحدة",
                           {"jobs": [{"id": r["id"], "error": (r["last_error"] or "")[:200]}
                                     for r in rows]})
    return DoctorCheck("jobs.failing", "مهام فشلت في 24 ساعة", CheckStatus.OK, "لا فواقد")


def check_outbox_stall(backend, settings, org) -> DoctorCheck:
    row = backend.system_one(
        """SELECT count(*) AS n, min(created_at) AS oldest FROM events.outbox
           WHERE published_at IS NULL""")
    if row["n"] == 0:
        return DoctorCheck("events.outbox", "مضخة الأحداث", CheckStatus.OK, "الـ outbox فاضي")
    age_min = backend.system_one(
        "SELECT round(extract(epoch FROM (now() - %s)) / 60) AS mins", (row["oldest"],))["mins"]
    if age_min >= 15:
        return DoctorCheck("events.outbox", "مضخة الأحداث", CheckStatus.FAIL,
                           f"{row['n']} حدث غير منشور وأقدمهم {age_min} دقيقة — الـ relay واقف",
                           {"pending": row["n"], "oldest_minutes": age_min})
    return DoctorCheck("events.outbox", "مضخة الأحداث", CheckStatus.OK,
                       f"{row['n']} في الطريق — طبيعي")


def check_dead_letters(backend, settings, org) -> DoctorCheck:
    rows = backend.system_all(
        """SELECT consumer, event_type, error, created_at FROM events.dead_letters
           WHERE created_at > now() - interval '24 hours' ORDER BY created_at DESC LIMIT 5""")
    if rows:
        return DoctorCheck("events.dead_letters", "رسائل ميتة (24س)", CheckStatus.FAIL,
                           f"{len(rows)} حدث استنفد محاولاته — السبب في evidence",
                           {"items": [{"consumer": r["consumer"], "type": r["event_type"],
                                       "error": (r["error"] or "")[:200]} for r in rows]})
    return DoctorCheck("events.dead_letters", "رسائل ميتة (24س)", CheckStatus.OK, "لا رسائل ميتة")


def check_uncertain_effects(backend, settings, org) -> DoctorCheck:
    row = backend.system_one(
        """SELECT count(*) AS n FROM effects.effect_ledger
           WHERE status = 'uncertain' AND reconciled_at IS NULL
             AND created_at < now() - interval '24 hours'""")
    if row["n"]:
        return DoctorCheck("effects.uncertain", "آثار خارجية غير محسومة", CheckStatus.WARN,
                           f"{row['n']} effect في حالة uncertain من غير حسم — محتاج reconciliation",
                           {"count": row["n"]})
    return DoctorCheck("effects.uncertain", "آثار خارجية غير محسومة", CheckStatus.OK, "نظيف")


def check_zero_candidate_runs(backend, settings, org) -> DoctorCheck:
    rows = backend.system_all(
        """SELECT id::text, job_type, finished_at FROM runtime.jobs
           WHERE state = 'PARTIAL_SUCCESS'
             AND finished_at > now() - interval '24 hours'
           ORDER BY finished_at DESC LIMIT 5""")
    if rows:
        return DoctorCheck("honesty.zero_candidates", "تشغيلات بلا مرشحين", CheckStatus.WARN,
                           f"{len(rows)} تشغيل خلص بلا مرشحين — راجع الـ ICP (مدن/كلمات)",
                           {"job_ids": [r["id"] for r in rows]})
    return DoctorCheck("honesty.zero_candidates", "تشغيلات بلا مرشحين", CheckStatus.OK, "لا تشغيلات فاضية")


def check_schedule_stalled(backend, settings, org) -> DoctorCheck:
    """No new job created anywhere in 26h = the daily schedule is broken.
    An n8n failure once ran silent for 17 days because nothing watched the
    scheduler itself — replacing a broken cron with another broken cron helps
    nobody unless THIS check exists."""
    rows = backend.system_all(
        """SELECT max(ts) AS latest FROM (
             SELECT created_at AS ts FROM engine.jobs
             UNION ALL
             SELECT created_at AS ts FROM runtime.jobs
           ) all_jobs""")
    latest = rows[0]["latest"] if rows else None
    if latest is None:
        return DoctorCheck("schedule.stalled", "جدولة التشغيل اليومي", CheckStatus.WARN,
                           "مفيش ولا job اتعمل — الجدولة مش شغالة أو مش متظبطة")
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)
    hours = round((datetime.now(timezone.utc) - latest).total_seconds() / 3600, 1)
    if hours > 26:
        return DoctorCheck("schedule.stalled", "جدولة التشغيل اليومي", CheckStatus.WARN,
                           f"آخر job اتعمل قبل {hours} ساعة — الجدولة اليومية واقفة",
                           {"hours_since_last_job": hours})
    return DoctorCheck("schedule.stalled", "جدولة التشغيل اليومي", CheckStatus.OK,
                       f"آخر job قبل {hours} ساعة")


def check_pii_plaintext(backend, settings, org) -> DoctorCheck:
    """Anti-silent-leak: plaintext email/phone must NEVER appear in the
    projection display blob. One hit = FAIL with the offending lead id."""
    if not org:
        # Without a tenant context FORCE RLS denies every row: probing the
        # NULLS-uuid tenant "passes" vacuously — a false green. Say so instead.
        return DoctorCheck("pii.plaintext", "تسريب PII في العروض", CheckStatus.WARN,
                           "متاح داخل سياق مؤسسة فقط — شغّل الفحص من سياق org")
    rows = backend.org_all(
        org,
        """SELECT id::text, display::text AS blob FROM projects.lead_projections
           WHERE org_id = current_setting('app.tenant_id', true)::uuid
             AND built_at > now() - interval '7 days'""")
    offenders = [r["id"] for r in rows
                 if PLAINTEXT_EMAIL_RE.search(r["blob"] or "")]
    if offenders:
        return DoctorCheck("pii.plaintext", "تسريب PII في العروض", CheckStatus.FAIL,
                           "إيميل صريح داخل display لعروض leads — ممنوع (المرجع للخزنة)",
                           {"lead_ids": offenders[:10]})
    return DoctorCheck("pii.plaintext", "تسريب PII في العروض", CheckStatus.OK, "نظيف")


def check_vault_roundtrip(backend, settings, org, vault) -> DoctorCheck:
    if not org:
        return DoctorCheck("pii.vault", "اختبار الخزنة الذاتي", CheckStatus.WARN,
                           "متاح داخل سياق مؤسسة فقط")
    from infrastructure.pii.vault import TenantVault

    tv = TenantVault(vault, org)
    value = f"doctor-selftest-{org[:8]}@invalid.invalid"
    ref = tv.store("email", value)
    plain = tv.decrypt(ref, "verification", actor="doctor-selftest")
    if plain != value:
        return DoctorCheck("pii.vault", "اختبار الخزنة الذاتي", CheckStatus.FAIL,
                           "فك التشفير رجّع قيمة مختلفة — الخزنة مكسورة",
                           {"ref": ref})
    return DoctorCheck("pii.vault", "اختبار الخزنة الذاتي", CheckStatus.OK,
                       "تشفير/فك/تدقيق اشتغلوا")


def check_provider_health(backend, settings, org, gateway) -> DoctorCheck:
    rows = backend.system_all(
        """SELECT provider_id,
                  count(*) FILTER (WHERE status = 'failed') AS failed,
                  count(*) FILTER (WHERE status = 'succeeded') AS ok,
                  max(created_at) AS last_call
           FROM effects.effect_ledger
           WHERE created_at > now() - interval '24 hours'
           GROUP BY provider_id ORDER BY provider_id""")
    dead = [r["provider_id"] for r in rows if r["failed"] >= 3 and r["ok"] == 0]
    summary = {r["provider_id"]: {"ok": r["ok"], "failed": r["failed"]} for r in rows}
    if dead:
        return DoctorCheck("providers.health", "صحة المزودين (24س)", CheckStatus.FAIL,
                           f"مزودون فاشلون بالكامل: {dead} — راجع المفاتيح أو التهيئة",
                           {"providers": summary})
    return DoctorCheck("providers.health", "صحة المزودين (24س)", CheckStatus.OK,
                       "لا مزود فاشل بالكامل", {"providers": summary})


def check_models(backend, settings, org, model_gateway) -> DoctorCheck:
    if model_gateway is None:
        return DoctorCheck("models.gateway", "بوابة النماذج", CheckStatus.WARN,
                           "غير مركّبة في هذه العملية")
    caps = {}
    for capability, adapters in model_gateway._adapters.items():  # noqa: SLF001
        caps[capability] = [type(a).__name__ for _, a in adapters]
    degraded = [cap for cap, names in caps.items()
                if names and all("Fake" in n for n in names)]
    if degraded:
        return DoctorCheck("models.gateway", "بوابة النماذج", CheckStatus.WARN,
                           f"قدرات شغالة بنموذج وهمي: {degraded} — ضع مفاتيح حقيقية",
                           {"capabilities": caps})
    return DoctorCheck("models.gateway", "بوابة النماذج", CheckStatus.OK,
                       "قدرات حقيقية مسجلة", {"capabilities": caps})


def check_workers_alive(backend, settings, org) -> DoctorCheck:
    row = backend.system_one(
        """SELECT count(*) AS workers,
                  round(extract(epoch FROM (now() - max(last_beat))) / 60) AS mins
           FROM runtime.worker_heartbeats""")
    if row["workers"] == 0:
        return DoctorCheck("workers.alive", "نبض الووركرز", CheckStatus.WARN,
                           "لا heartbeats — الووركر مش شغال أو قديم عن هذه القاعدة")
    if row["mins"] >= 15:
        return DoctorCheck("workers.alive", "نبض الووركرز", CheckStatus.FAIL,
                           f"آخر نبضة قبل {row['mins']} دقيقة — الووركر ساقط",
                           {"workers": row["workers"], "minutes": row["mins"]})
    return DoctorCheck("workers.alive", "نبض الووركرز", CheckStatus.OK,
                       f"{row['workers']} ووركر حي (آخر نبضة {row['mins']} دقيقة)")


def check_stale_approvals(backend, settings, org) -> DoctorCheck:
    row = backend.system_one(
        """SELECT count(*) AS n FROM agents.approvals
           WHERE status = 'pending' AND created_at < now() - interval '48 hours'""")
    if row["n"]:
        return DoctorCheck("agent.approvals_stale", "موافقات معلقة طويلًا", CheckStatus.WARN,
                           f"{row['n']} موافقة معلقة من أكثر من 48 ساعة",
                           {"count": row["n"]})
    return DoctorCheck("agent.approvals_stale", "موافقات معلقة طويلًا", CheckStatus.OK, "لا معلقات")


def check_stale_alerts_open(backend, settings, org) -> DoctorCheck:
    row = backend.system_one(
        "SELECT count(*) AS n FROM runtime.alerts WHERE resolved_at IS NULL")
    if row["n"]:
        return DoctorCheck("sentinel.open_alerts", "تنبيهات مفتوحة", CheckStatus.WARN,
                           f"{row['n']} تنبيه سابق لسه مفتوح — راجع تاريخ التنبيهات",
                           {"count": row["n"]})
    return DoctorCheck("sentinel.open_alerts", "تنبيهات مفتوحة", CheckStatus.OK, "لا تنبيهات مفتوحة")


def check_orphaned_jobs(backend, settings, org) -> DoctorCheck:
    """QUEUED jobs whose tenant organization no longer exists — they can
    never succeed and they starve the queue.starved signal.

    Org existence is verified SELF-SCOPED per job (tenant set to the job's
    own org): the doctor's system queries cannot read platform.organizations
    through FORCE RLS, so a naive NOT EXISTS reports every job as orphaned."""
    rows = backend.system_all(
        "SELECT id::text, org_id::text AS org_id FROM runtime.jobs WHERE state = 'QUEUED'")
    orphans = [r for r in rows if not backend.org_exists(r["org_id"])]
    if orphans:
        return DoctorCheck("queue.orphaned", "مهام يتيمة (مؤسستها محذوفة)", CheckStatus.FAIL,
                           f"{len(orphans)} مهمة منتظرة لمؤسسات محذوفة — لا يمكن أن تنجح أبدًا",
                           {"job_ids": [r["id"] for r in orphans[:10]]})
    return DoctorCheck("queue.orphaned", "مهام يتيمة (مؤسستها محذوفة)", CheckStatus.OK, "لا مهام يتيمة")


def check_verification_quality(backend, settings, org) -> DoctorCheck:
    """UNKNOWN verification = the worker network couldn't reach SMTP (port 25
    blocked on residential ISPs). Honest status — but a run full of UNKNOWNs
    means scores are degraded and the operator should run the worker from a
    network (or host) that allows outbound SMTP."""
    if not org:
        return DoctorCheck("verify.quality", "جودة التحقق (24س)", CheckStatus.WARN,
                           "متاح داخل سياق مؤسسة فقط")
    rows = backend.org_all(
        org,
        """SELECT status, count(*) AS n FROM intelligence.verification_records
           WHERE org_id = current_setting('app.tenant_id', true)::uuid
             AND verified_at > now() - interval '24 hours'
           GROUP BY status""")
    if not rows:
        return DoctorCheck("verify.quality", "جودة التحقق (24س)", CheckStatus.OK,
                           "لا تحققات في 24 ساعة")
    total = sum(r["n"] for r in rows)
    by = {r["status"]: r["n"] for r in rows}
    unknown = by.get("UNKNOWN", 0)
    if unknown == total:
        return DoctorCheck("verify.quality", "جودة التحقق (24س)", CheckStatus.WARN,
                           f"كل التحققات ({total}) UNKNOWN — شبكة الووركر مانعة SMTP الصادر (بورت 25)؛ شغّل الووركر من شبكة تسمح أو من الاستضافة",
                           {"by_status": by})
    if unknown:
        return DoctorCheck("verify.quality", "جودة التحقق (24س)", CheckStatus.WARN,
                           f"{unknown} من {total} تحقق UNKNOWN — جزئيًا بسبب شبكة الووركر",
                           {"by_status": by})
    return DoctorCheck("verify.quality", "جودة التحقق (24س)", CheckStatus.OK,
                       "التحققات تمام", {"by_status": by})


def check_http_surface(backend, settings, org) -> DoctorCheck:
    """Black-box probe of the DEPLOYED app's critical HTTP surface.

    Internal checks (DB, queue, vault) can all be green while the deployed
    site 500s — today's outage class. This check hits the public origin
    exactly like a browser/client would and FAILS with the endpoint +
    status + error on any deviation."""
    import httpx

    base = (settings.public_base_url or "").rstrip("/")
    if not base:
        return DoctorCheck("http.surface", "فحص سطح HTTP المنشور", CheckStatus.WARN,
                           "لا يوجد LEAD_ENGINE_PUBLIC_BASE_URL — الفحص الأسود متوقف")
    token = (settings.service_token or "").strip()
    auth = {"Authorization": f"Bearer {token}"} if token else {}
    probes = [
        ("GET", "/health", None),
        ("GET", "/v6/healthz", None),
        ("GET", "/api/status", None),
        ("GET", "/api/v1/review/pending", auth),
        ("GET", "/api/v1/icps", auth),
        ("GET", "/api/analytics", auth),
    ]
    failures = []
    latencies = []
    try:
        with httpx.Client(timeout=httpx.Timeout(20.0)) as client:
            for method, path, headers in probes:
                t0 = time.monotonic()
                try:
                    resp = client.request(method, base + path, headers=headers or {})
                    ms = round((time.monotonic() - t0) * 1000, 1)
                    latencies.append({"path": path, "status": resp.status_code, "ms": ms})
                    if resp.status_code >= 500:
                        failures.append(f"{method} {path} -> {resp.status_code}")
                except Exception as exc:  # noqa: BLE001 — the failure IS the finding
                    failures.append(f"{method} {path} -> {type(exc).__name__}: {exc}")
    except Exception as exc:  # noqa: BLE001
        return DoctorCheck("http.surface", "فحص سطح HTTP المنشور", CheckStatus.FAIL,
                           f"تعذر الوصول للنشر أصلًا: {exc}", {"base": base})
    if failures:
        return DoctorCheck("http.surface", "فحص سطح HTTP المنشور", CheckStatus.FAIL,
                           "؛ ".join(failures), {"latencies": latencies})
    slow = [probe for probe in latencies if probe["ms"] > 5000]
    if slow:
        return DoctorCheck("http.surface", "فحص سطح HTTP المنشور", CheckStatus.WARN,
                           f"endpoints بطيئة: {[(s['path'], s['ms']) for s in slow]}",
                           {"latencies": latencies})
    return DoctorCheck("http.surface", "فحص سطح HTTP المنشور", CheckStatus.OK,
                       f"{len(latencies)} endpoint كلهم 200",
                       {"latencies": latencies})
