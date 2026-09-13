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
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useLiveData } from "@/hooks/useLiveData";
import { apiGet, apiGetExtra } from "@/lib/api";
import { cn, formatNumber } from "@/lib/utils";
import { Loader2 } from "lucide-react";
import { friendlyError } from "@/lib/friendly";
import { PageHeader } from "@/components/layout/PageHeader";
import { Spinner } from "@/components/ui/EmptyState";
import { StatCard } from "@/components/ui/FilterPills";
import { toast } from "sonner";

type ServiceRow = {
  name: string; icon: React.ReactNode; reachable: boolean; degraded: boolean;
  detail: string;
};

export function CommandCenterPage() {
  const { data: status, loading, refresh } = useLiveData(() => apiGet.status(), 5000);
  const { data: conflictsData } = useLiveData(() => apiGetExtra.conflicts("OPEN"), 10000);
  const { data: activity } = useLiveData(() => apiGet.activity(12), 5000);
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

  if (loading && !status) return <Spinner />;

  return (
    <div className="space-y-6">
      <PageHeader
        icon={<Radio className="h-5 w-5" />}
        title="مركز القيادة"
        description="صورة حية للنظام كله — كل رقم من قاعدة البيانات الحقيقية"
        action={
          <Button variant="outline" onClick={refresh} className="text-[12px] h-8">
            <RefreshCw className="h-3.5 w-3.5" /> تحديث
          </Button>
        }
      />

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
        <StatCard label="تعارضات" value={formatNumber(openConflicts)} icon={ShieldAlert} tone="warn" />
        <StatCard label="مهام فاشلة" value={formatNumber(failedJobs)} icon={XCircle} tone="danger" />
        <StatCard label="مفاتيح مفعلة" value={formatNumber(providers.filter((p) => p.key_state === "set" || p.key_state === "local").length)}
                  icon={Zap} tone="info" />
        <StatCard label="إجمالي الـleads" value={formatNumber(status?.leads_total || 0)} icon={Database} />
      </div>

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
              {(activity?.events || []).length === 0 ? (
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
