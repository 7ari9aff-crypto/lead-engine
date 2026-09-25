/**
 * Command Center — the single live view of the whole platform (design adopted
 * from the approved prototype, wired to REAL data): services health, metric
 * cards, live activity feed, and actionable alerts. Every number comes from
 * the running system, never hardcoded.
 */
import { useMemo, useState } from "react";
import {
  Activity, AlertTriangle, Brain, Briefcase, CheckCircle2, Cpu, Database,
  Search, Server, XCircle, Zap, Bot, Radio, RefreshCw, ShieldAlert, Bot as Runtime,
  Gauge, Timer, ShieldCheck,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { apiGet, apiGetExtra, type StatusResponse, type SloSummary } from "@/lib/api";
import { useInstantQuery } from "@/hooks/useInstantQuery";
import { useSyncExternalStore } from "react";
import { liveStore } from "@/lib/liveStore";
import { cn, formatNumber } from "@/lib/utils";
import { Loader2 } from "lucide-react";
import { friendlyError } from "@/lib/friendly";
import { PageHeader } from "@/components/layout/PageHeader";
import { Spinner } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { StaleBanner } from "@/components/ui/StaleBanner";
import { StatCard } from "@/components/ui/FilterPills";
import { toast } from "sonner";

type ServiceRow = {
  name: string; icon: React.ReactNode; reachable: boolean; degraded: boolean;
  detail: string;
};

export function CommandCenterPage() {
  // Instant by construction: first paint from the last known-good payload,
  // then the shared SSE bridge pushes every change (no 5s polling).
  const { data: status, isLoading, error: statusError, refetch } = useInstantQuery<StatusResponse>(
    ["status"], () => apiGet.status(), { staleTime: 5_000, refetchInterval: 30_000 });
  const { data: conflictsData, error: conflictsError } = useInstantQuery(
    ["conflicts", "OPEN"], () => apiGetExtra.conflicts("OPEN"), { staleTime: 30_000 });
  const { data: activity, error: activityError } = useInstantQuery(
    ["activity", 12], () => apiGet.activity(12), { staleTime: 15_000, refetchInterval: 30_000 });
  const live = useSyncExternalStore(liveStore.subscribe, liveStore.getSnapshotState);
  const [openmanus, setOpenmanus] = useState<any>(null);
  const [probing, setProbing] = useState(false);

  const probeRuntime = async () => {
    setProbing(true);
    try {
      const { api } = await import("@/lib/api");
      setOpenmanus(await api.get("/api/v1/research/openmanus/health"));
    } catch (e) {
      toast.error(friendlyError(e));
    } finally {
      setProbing(false);
    }
  };

  const providers = status?.providers || [];
  const exhausted = providers.filter((p) => p.status === "exhausted");
  const cooldown = providers.filter((p) => p.status === "cooldown");
  const missingKeys = providers.filter((p) => p.key_state === "missing");
  const jobsByState = status?.jobs_by_state || {};
  const researchLive = (jobsByState.RUNNING || 0) + (jobsByState.DISCOVERING || 0) +
    (jobsByState.RESEARCHING || 0) + (jobsByState.VERIFYING || 0) + (jobsByState.QUALIFYING || 0);
  const pausedJobs = (jobsByState.PAUSED || 0) + (jobsByState.RESUMING || 0) +
    (jobsByState.WAITING_FOR_USER || 0);
  const failedJobs = jobsByState.FAILED || 0;
  const reviewLeads = status?.leads_by_stage?.REVIEW || 0;
  const openConflicts = conflictsData?.conflicts?.length || 0;

  // SLO panel — the reliability numbers operators are held to. Targets live in
  // the backend (metrics_api.SLO_TARGETS), so this card can never drift from
  // what the API itself calls "healthy".
  const { data: slo, error: sloError } = useInstantQuery<SloSummary>(
    ["slo"],
    () => apiGet.slo(),
    { staleTime: 15_000, refetchInterval: 60_000 }
  );

  const services: ServiceRow[] = useMemo(() => {
    const rows: ServiceRow[] = [
      { name: "Lead Engine API", icon: <Cpu className="h-4 w-4" />, reachable: true, degraded: false,
        detail: `v${status?.version || "?"} · Python ${status?.system?.python || ""}` },
      { name: "قاعدة البيانات", icon: <Database className="h-4 w-4" />,
        reachable: !!status?.system?.supabase_configured || !!status?.system?.db_path,
        degraded: !status?.system?.supabase_configured,
        detail: status?.system?.supabase_configured ? "Supabase Postgres متصل" : "SQLite محلي (dev)" },
      { name: "مزودو البحث", icon: <Search className="h-4 w-4" />,
        reachable: providers.some((p) => p.type === "search" && p.key_state !== "missing"),
        degraded: providers.filter((p) => p.type === "search").every((p) => p.key_state === "missing"),
        detail: providers.filter((p) => p.type === "search").map((p) => p.name).join(" · ") || "—" },
      { name: "النماذج اللغوية", icon: <Brain className="h-4 w-4" />,
        reachable: providers.some((p) => p.type === "llm" && p.key_state !== "missing"),
        degraded: providers.filter((p) => p.type === "llm").every((p) => p.key_state === "missing"),
        detail: providers.filter((p) => p.type === "llm").map((p) => p.name).join(" · ") || "—" },
      { name: "طابور المهام", icon: <Server className="h-4 w-4" />, reachable: true, degraded: false,
        detail: `حية: ${formatNumber(researchLive)} · موقوفة: ${formatNumber(pausedJobs)}` },
    ];
    if (openmanus) {
      rows.push({
        name: "OpenManus Runtime", icon: <Runtime className="h-4 w-4" />,
        reachable: !!openmanus.reachable, degraded: !openmanus.reachable,
        detail: openmanus.reachable
          ? `${openmanus.engine || "runner"} · ${openmanus.openmanus_entry || ""}`
          : (openmanus.note || openmanus.error || "غير متاح"),
      });
    }
    return rows;
  }, [status, providers, openmanus, researchLive, pausedJobs]);

  const healthy = services.filter((s) => s.reachable && !s.degraded).length;
  const degradedCount = services.filter((s) => s.degraded || !s.reachable).length;
  const overall = degradedCount === 0 ? "HEALTHY" : healthy > 0 ? "DEGRADED" : "DOWN";

  const alerts = useMemo(() => {
    const out: { level: "warn" | "danger"; text: string }[] = [];
    if (exhausted.length) out.push({ level: "danger",
      text: `مزودون استنفدوا حصصهم: ${exhausted.map((p) => p.name).join("، ")}` });
    if (openConflicts) out.push({ level: "warn",
      text: `${openConflicts} تعارض بيانات مفتوح — محتاج قرارك في لوحة المراجعة` });
    if (failedJobs) out.push({ level: "danger", text: `${failedJobs} مهمة فاشلة` });
    if (pausedJobs) out.push({ level: "warn", text: `${pausedJobs} مهمة موقوفة (سعة/انتظار)` });
    if (cooldown.length) out.push({ level: "warn",
      text: `مزودون في تبريد: ${cooldown.map((p) => p.name).join("، ")}` });
    return out;
  }, [exhausted, cooldown, openConflicts, failedJobs, pausedJobs]);

  if (isLoading && !status) return <Spinner />;
  // Every card on this page derives from `status`. Without it the page is a
  // wall of zeroes describing a system that is broken, not idle (FAIL-01).
  if (statusError && !status) {
    return (
      <ErrorState
        error={statusError}
        onRetry={() => void refetch()}
        subject="مركز القيادة"
        className="m-4"
      />
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        icon={<Radio className="h-5 w-5" />}
        title="مركز القيادة"
        description="صورة حية للنظام كله — كل رقم من قاعدة البيانات الحقيقية"
        action={
          <>
            <span
              className={cn(
                "hidden sm:flex items-center gap-1.5 h-8 px-2.5 rounded-lg border text-[12px] font-medium",
                live.state === "live"
                  ? "border-[var(--success)]/40 bg-[color-mix(in_srgb,var(--success)_10%,transparent)] text-[var(--success)]"
                  : "border-[var(--border-soft)] bg-[var(--bg-soft)] text-[var(--fg-muted)]"
              )}
              title={live.state === "live" ? "متصل مباشرًا" : "جارٍ الاتصال…"}
            >
              <span className={cn("h-2 w-2 rounded-full",
                live.state === "live" ? "bg-[var(--success)] animate-pulse" : "bg-[var(--fg-soft)]")} />
              {live.state === "live" ? "مباشر" : "اتصال…"}
            </span>
            <Button
              variant="outline"
              className="text-[12px] h-8"
              onClick={() => { void refetch(); liveStore.refresh(); }}
            >
              <RefreshCw className="h-3.5 w-3.5" /> تحديث
            </Button>
          </>
        }
      />

      {(conflictsError || activityError || sloError) && (
        <StaleBanner
          error={conflictsError || activityError || sloError}
          subject="بعض بطاقات مركز القيادة"
          onRetry={() => { void refetch(); liveStore.refresh(); }}
        />
      )}

      {/* overall status bar */}
      <div className="flex items-center gap-3 px-4 py-3 rounded-xl border border-[var(--border-soft)] bg-[var(--bg-elev)]">
        <span className={cn("h-2 w-2 rounded-full",
          overall === "HEALTHY" ? "bg-emerald-500 animate-pulse"
          : overall === "DEGRADED" ? "bg-amber-500" : "bg-rose-500")} />
        <span className="text-[13.5px] font-bold">
          النظام: {overall === "HEALTHY" ? "سليم" : overall === "DEGRADED" ? "متدهور جزئيًا" : "متوقف"}
        </span>
        <span className="text-[11.5px] text-[var(--fg-muted)]">
          {healthy} خدمة سليمة{degradedCount ? ` · ${degradedCount} متدهورة` : ""}
        </span>
        <div className="ms-auto flex items-center gap-2">
          {alerts.length > 0 && (
            <Badge variant={alerts.some((a) => a.level === "danger") ? "danger" : "warn"}>
              <AlertTriangle className="h-3 w-3 inline me-1" />{alerts.length} تنبيه
            </Badge>
          )}
          <Button variant="outline" className="text-[11px] h-7" onClick={probeRuntime} disabled={probing}>
            {probing ? <Loader2 className="h-3 w-3 animate-spin" /> : <Runtime className="h-3 w-3" />}
            فحص OpenManus
          </Button>
        </div>
      </div>

      {/* metric cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <StatCard label="بحث حي" value={formatNumber(researchLive)} icon={Briefcase} />
        <StatCard label="جاهزة للمراجعة" value={formatNumber(reviewLeads)} icon={CheckCircle2} />
        <StatCard
          label="تعارضات"
          value={conflictsError && !conflictsData ? "غير متاح" : formatNumber(openConflicts)}
          icon={ShieldAlert}
          tone="warn"
        />
        <StatCard label="مهام فاشلة" value={formatNumber(failedJobs)} icon={XCircle} tone="danger" />
        <StatCard label="مفاتيح مفعلة" value={formatNumber(providers.filter((p) => p.key_state === "set" || p.key_state === "local").length)}
                  icon={Zap} tone="info" />
        <StatCard label="إجمالي الـleads" value={formatNumber(status?.leads_total || 0)} icon={Database} />
      </div>

      <SloPanel slo={slo} />

      <div className="grid lg:grid-cols-2 gap-4">
        {/* services */}
        <Card>
          <CardContent className="p-4 space-y-2">
            <div className="text-[12px] font-semibold text-[var(--fg-soft)] mb-1">الخدمات</div>
            {services.map((s) => (
              <div key={s.name} className="flex items-center gap-2.5 rounded-lg border border-[var(--border-soft)] px-3 py-2">
                <span className={cn(s.reachable && !s.degraded ? "text-emerald-500" : "text-amber-500")}>{s.icon}</span>
                <span className="text-[12.5px] font-medium">{s.name}</span>
                <span className="ms-auto text-[10.5px] text-[var(--fg-soft)] truncate max-w-[45%]">{s.detail}</span>
                <Badge variant={s.reachable && !s.degraded ? "success" : "warn"} className="text-[9px] shrink-0">
                  {s.reachable ? (s.degraded ? "متدهورة" : "سليمة") : "غير متاحة"}
                </Badge>
              </div>
            ))}
          </CardContent>
        </Card>

        {/* alerts + activity */}
        <div className="space-y-4">
          {alerts.length > 0 && (
            <Card className="border-amber-500/40">
              <CardContent className="p-4 space-y-2">
                <div className="text-[12px] font-semibold text-[var(--fg-soft)] flex items-center gap-1.5">
                  <AlertTriangle className="h-3.5 w-3.5 text-amber-500" /> تنبيهات تحتاج انتباهك
                </div>
                {alerts.map((a, i) => (
                  <div key={i} className={cn("text-[12px] leading-5 rounded-lg px-2.5 py-1.5",
                    a.level === "danger"
                      ? "bg-rose-500/10 text-rose-600 dark:text-rose-400"
                      : "bg-amber-500/10 text-amber-700 dark:text-amber-400")}>
                    {a.text}
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          <Card>
            <CardContent className="p-4">
              <div className="text-[12px] font-semibold text-[var(--fg-soft)] mb-2 flex items-center gap-1.5">
                <Activity className="h-3.5 w-3.5" /> النشاط الحي
              </div>
              {activityError && !activity ? (
                <div className="text-[12px] text-[var(--danger)] py-2" role="alert">
                  تعذر تحميل النشاط الحي — {friendlyError(activityError)}
                </div>
              ) : (activity?.events || []).length === 0 ? (
                <div className="text-[12px] text-[var(--fg-muted)] py-2">لا نشاط مسجل بعد.</div>
              ) : (
                <div className="space-y-1.5 max-h-72 overflow-y-auto">
                  {activity!.events.map((ev) => (
                    <div key={ev.id} className="flex items-start gap-2 text-[11.5px]">
                      <span className="text-[var(--fg-soft)] tnum shrink-0">{ev.ts?.slice(11, 19)}</span>
                      <span className="font-mono text-[var(--accent)] shrink-0">{ev.kind}</span>
                      <span className="text-[var(--fg-muted)] truncate">{JSON.stringify(ev.payload || {}).slice(0, 80)}</span>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

/**
 * SLO panel — availability / error rate / p95 latency against the targets the
 * backend publishes, plus the rolling uptime. While the process is still cold
 * (`warming_up`) the verdict is deliberately withheld instead of faked green.
 */
function SloPanel({ slo }: { slo?: SloSummary }) {
  const observed = slo?.observed;
  const targets = slo?.targets;

  const rows: { label: string; value: string; ok: boolean | null; hint?: string }[] = [
    {
      label: "التوافر",
      value: observed ? `${(observed.availability * 100).toFixed(2)}%` : "—",
      ok: slo ? slo.checks.availability : null,
      hint: targets ? `الهدف ≥ ${(targets.availability * 100).toFixed(1)}%` : undefined,
    },
    {
      label: "معدل الأخطاء",
      value: observed ? `${(observed.error_rate * 100).toFixed(2)}%` : "—",
      ok: slo ? slo.checks.error_rate : null,
      hint: targets ? `الهدف ≤ ${(targets.error_rate * 100).toFixed(1)}%` : undefined,
    },
    {
      label: "زمن الاستجابة p95",
      value: observed ? `${observed.latency_p95_ms.toFixed(0)} ms` : "—",
      ok: slo ? slo.checks.latency_p95 : null,
      hint: targets ? `الهدف ≤ ${targets.latency_p95_ms.toFixed(0)} ms` : undefined,
    },
    {
      label: "زمن الاستجابة p50",
      value: observed ? `${observed.latency_p50_ms.toFixed(0)} ms` : "—",
      ok: null,
    },
  ];

  const verdict = slo
    ? slo.warming_up
      ? "warmup"
      : slo.within_slo
        ? "ok"
        : "breach"
    : "unknown";

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <div className="flex items-center gap-2 flex-wrap">
          <Gauge className="h-4 w-4 text-[var(--accent)]" />
          <span className="text-[12px] font-semibold text-[var(--fg-soft)]">
            مستوى الخدمة (SLO)
          </span>
          <Badge
            variant={verdict === "ok" ? "success" : verdict === "breach" ? "danger" : "warn"}
            className="text-[9px]"
          >
            {verdict === "ok"
              ? "داخل الهدف"
              : verdict === "breach"
                ? "تجاوز الحد"
                : verdict === "warmup"
                  ? "قيد التسخين"
                  : "غير معروف"}
          </Badge>
          {observed && (
            <span className="ms-auto text-[10.5px] text-[var(--fg-soft)] flex items-center gap-1.5">
              <Timer className="h-3 w-3" />
              تشغيل {formatUptime(observed.uptime_seconds)} · {formatNumber(observed.requests_total)} طلب
            </span>
          )}
        </div>

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
          {rows.map((r) => (
            <div
              key={r.label}
              className={cn(
                "rounded-lg border px-3 py-2",
                r.ok === null
                  ? "border-[var(--border-soft)] bg-[var(--bg-soft)]"
                  : r.ok
                    ? "border-emerald-500/30 bg-emerald-500/5"
                    : "border-rose-500/40 bg-rose-500/5"
              )}
            >
              <div className="text-[10.5px] text-[var(--fg-soft)]">{r.label}</div>
              <div className="text-[15px] font-bold tnum mt-0.5">{r.value}</div>
              {r.hint && <div className="text-[10px] text-[var(--fg-soft)] mt-0.5">{r.hint}</div>}
            </div>
          ))}
        </div>

        {verdict === "breach" && (
          <div className="text-[11.5px] rounded-lg px-2.5 py-1.5 bg-rose-500/10 text-rose-600 dark:text-rose-400 flex items-start gap-1.5">
            <ShieldCheck className="h-3.5 w-3.5 mt-0.5 shrink-0" />
            أحد مؤشرات مستوى الخدمة خارج الهدف — راجع الخدمات والتنبيهات بالأسفل.
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/** Human uptime: "3ي 4س" style, kept short because it sits inline in a badge row. */
function formatUptime(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds || 0));
  if (s < 60) return `${s} ث`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} د`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} س ${m % 60} د`;
  return `${Math.floor(h / 24)} ي ${h % 24} س`;
}
