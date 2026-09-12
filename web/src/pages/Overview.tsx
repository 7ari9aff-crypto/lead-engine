import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  Users,
  Briefcase,
  Activity,
  CheckCircle2,
  AlertTriangle,
  Database,
  Trash2,
  Layers,
  Cpu,
  HardDrive,
  TrendingUp,
  TrendingDown,
  Minus,
  ArrowUpRight,
  Clock,
  Zap,
  ListChecks,
  X,
  KeyRound,
  PlayCircle,
  Plug,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Badge, StatusDot } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { apiGet, apiPost, type ProviderRow } from "@/lib/api";
import { formatNumber, relativeTime, truncate } from "@/lib/utils";
import { friendlyError, ICP_LABELS } from "@/lib/friendly";
import { toast } from "sonner";
import { PageSkeleton } from "@/components/ui/Skeleton";
import {
  AreaChart, Area, BarChart, Bar, ResponsiveContainer,
  XAxis, YAxis, Tooltip, CartesianGrid, Cell,
} from "recharts";
import { cn } from "@/lib/utils";

const CHECKLIST_DONE_KEY = "leadEngine.checklistDismissed";

export function OverviewPage() {
  const { data, isLoading, refetch } = useQuery({
    queryKey: ["status"],
    queryFn: apiGet.status,
    refetchInterval: 5000,
  });

  const { data: analytics } = useQuery({
    queryKey: ["analytics"],
    queryFn: apiGet.analytics,
    refetchInterval: 15000,
  });

  const { data: integrationsData } = useQuery({
    queryKey: ["integrations"],
    queryFn: apiGet.integrations,
    refetchInterval: 60000,
  });

  const [checklistHidden, setChecklistHidden] = useState(
    () => localStorage.getItem(CHECKLIST_DONE_KEY) === "1"
  );

  if (isLoading && !data) return <PageSkeleton />;

  const providers = data?.providers ?? [];
  const recentJobs = data?.recent_jobs ?? [];
  const usage = data?.usage_totals ?? [];
  const leadsByStage = data?.leads_by_stage ?? {};
  const cacheEntries = data?.cache_entries ?? {};
  const jobsByState = data?.jobs_by_state ?? {};

  const leadsAccepted = leadsByStage.ACCEPTED || 0;
  const leadsReview = leadsByStage.REVIEW || 0;
  const leadsTotal = data?.leads_total ?? 0;
  const totalUnits = providers.reduce((sum, p) => sum + (p.quota_used || 0), 0);
  const healthy = providers.filter((p) => p.status === "active").length;
  const degraded = providers.filter((p) => ["degraded", "exhausted", "cooldown", "disabled"].includes(p.status)).length;
  const running = jobsByState.RUNNING || 0;
  const queued = jobsByState.QUEUED || 0;
  const paused = jobsByState.PAUSED || 0;

  // Trend calculations from analytics
  const leadsTrend = calcTrend(analytics?.leads_over_time ?? []);
  const usageTrend = calcTrend(analytics?.usage_over_time ?? []);

  // Setup checklist — the Apollo-style "Next steps for you"
  const hasKey = providers.some((p) => p.key_state === "set" || p.key_state === "local");
  const hasJob = recentJobs.length > 0 || leadsTotal > 0;
  const hasLead = leadsTotal > 0;
  const hasIntegration = (integrationsData?.integrations ?? []).some((i: any) => i.connected);
  const checklistSteps = [
    { done: hasKey, label: "اربط أول مفتاح مزود", desc: "بدون مفتاح المحرك بيمشي على الوضع المحلي فقط", href: "/keys", icon: KeyRound },
    { done: hasJob, label: "شغّل أول مهمة توليد", desc: "جولة كاملة تستغرق دقائق وبتحدّث كل شئ تلقائيًا", href: "/jobs", icon: PlayCircle },
    { done: hasLead, label: "استلم أول عميل محتمل", desc: "النتائج المقبولة تظهر في صفحة النتائج", href: "/leads", icon: Users },
    { done: hasIntegration, label: "اربط تكامل خارجي — اختياري", desc: "جيميل أو هاب سبوت للمتابعة المباشرة", href: "/integrations", icon: Plug },
  ];
  const checklistDone = checklistSteps.filter((s) => s.done).length;
  const checklistComplete = checklistDone === checklistSteps.length;

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2.5">
            <span className="flex items-center justify-center h-8 w-8 rounded-lg gradient-bg">
              <Zap className="h-4 w-4 text-[var(--accent)]" />
            </span>
            نظرة عامة على النظام
          </h1>
          <p className="text-sm text-[var(--fg-muted)] mt-1.5">
            حالة المحرك في الوقت الفعلي — كل الأرقام مباشرة من قاعدة البيانات.
          </p>
        </div>
      </div>

      {/* Setup checklist */}
      {!checklistHidden && !checklistComplete && (
        <Card className="border-[var(--accent)]/40">
          <CardContent className="p-5">
            <div className="flex items-center justify-between gap-3 mb-3.5">
              <div className="flex items-center gap-2.5">
                <span className="h-8 w-8 rounded-lg bg-[var(--accent-soft)] text-[var(--accent)] flex items-center justify-center">
                  <ListChecks className="h-4 w-4" />
                </span>
                <div>
                  <div className="text-sm font-bold">خطوات البدء</div>
                  <div className="text-[11px] text-[var(--fg-soft)]">
                    خلصت {checklistDone} من {checklistSteps.length} — المنصة بتشتغل كاملة لما تخلص القايمة
                  </div>
                </div>
              </div>
              <Button
                variant="ghost"
                size="icon-sm"
                title="إخفاء القايمة"
                onClick={() => {
                  localStorage.setItem(CHECKLIST_DONE_KEY, "1");
                  setChecklistHidden(true);
                }}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
            <div className="h-1.5 rounded-full bg-[var(--bg-soft)] overflow-hidden mb-3.5">
              <div
                className="h-full rounded-full bg-[var(--accent)] transition-all"
                style={{ width: `${(checklistDone / checklistSteps.length) * 100}%` }}
              />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-2.5">
              {checklistSteps.map((s) => {
                const Icon = s.icon;
                return (
                  <button
                    key={s.label}
                    onClick={() => { if (!s.done) window.location.assign(s.href); }}
                    className={cn(
                      "text-right rounded-xl border p-3.5 transition-all group",
                      s.done
                        ? "border-[var(--success)]/40 bg-[color-mix(in_srgb,var(--success)_6%,transparent)]"
                        : "border-[var(--border)] hover:border-[var(--accent)] hover:shadow-[var(--shadow)]"
                    )}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <Icon className={cn("h-4 w-4", s.done ? "text-[var(--success)]" : "text-[var(--accent)]")} />
                      {s.done ? (
                        <CheckCircle2 className="h-4 w-4 text-[var(--success)]" />
                      ) : (
                        <ArrowUpRight className="h-3.5 w-3.5 text-[var(--fg-soft)] opacity-0 group-hover:opacity-100 transition-opacity" />
                      )}
                    </div>
                    <div className={cn("text-[13px] font-medium", s.done && "text-[var(--fg-muted)] line-through")}>
                      {s.label}
                    </div>
                    {!s.done && <div className="text-[11px] text-[var(--fg-soft)] mt-1 leading-4">{s.desc}</div>}
                  </button>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Metric cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MetricCard
          icon={<CheckCircle2 className="h-5 w-5" />}
          label="عملاء مقبولون"
          value={formatNumber(leadsAccepted)}
          color="success"
          trend={leadsTrend}
        />
        <MetricCard
          icon={<AlertTriangle className="h-5 w-5" />}
          label="تحت المراجعة"
          value={formatNumber(leadsReview)}
          color="warn"
        />
        <MetricCard
          icon={<Briefcase className="h-5 w-5" />}
          label="مهام جارية"
          value={formatNumber(running + queued)}
          color="info"
          sub={`${running} شغّال · ${queued} بالانتظار · ${paused} موقّفة`}
        />
        <MetricCard
          icon={<Cpu className="h-5 w-5" />}
          label="وحدات مستهلكة"
          value={formatNumber(totalUnits)}
          color="accent"
          trend={usageTrend}
        />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>
              <TrendingUp className="h-4 w-4 text-[var(--accent)]" />
              العملاء المحتملون عبر الوقت
            </CardTitle>
            <CardDescription>آخر 30 يوم</CardDescription>
          </CardHeader>
          <CardContent>
            <LeadsAreaChart data={analytics?.leads_over_time ?? []} />
          </CardContent>
        </Card>

        <ProviderHealthChart providers={providers} healthy={healthy} degraded={degraded} />
      </div>

      {/* Usage + Jobs row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>
              <Activity className="h-4 w-4 text-[var(--accent)]" />
              استهلاك المزوّدين
            </CardTitle>
            <CardDescription>أعلى المزوّدين استهلاكًا للوحدات</CardDescription>
          </CardHeader>
          <CardContent>
            <UsageBarChart data={usage} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>
              <Clock className="h-4 w-4 text-[var(--info)]" />
              آخر المهام
            </CardTitle>
            <CardDescription>{Math.min(6, recentJobs.length)} مهمة</CardDescription>
          </CardHeader>
          <CardContent className="space-y-1.5 max-h-[340px] overflow-y-auto">
            {recentJobs.length === 0 ? (
              <EmptyState icon={<Briefcase className="h-7 w-7" />} title="لا توجد مهام بعد" />
            ) : (
              recentJobs.slice(0, 6).map((j) => (
                <div
                  key={j.job_id}
                  className="flex items-center justify-between gap-2 rounded-lg p-2.5 hover:bg-[var(--bg-hover)] transition-colors"
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <StatusDot status={j.state} />
                    <div className="min-w-0">
                      <div className="font-medium text-sm truncate">{ICP_LABELS[j.icp_id] ?? "مهمة توليد عملاء"}</div>
                      <div className="text-xs text-[var(--fg-soft)]">
                        {j.created_at ? relativeTime(j.created_at) : "—"}
                      </div>
                    </div>
                  </div>
                  <JobStateBadge state={j.state} />
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </div>

      {/* Provider list + cache */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>
              <Layers className="h-4 w-4 text-[var(--accent)]" />
              حالة المزوّدين
            </CardTitle>
            <CardDescription>{healthy} صحّي · {degraded} منخفض · {providers.length} إجمالي</CardDescription>
          </CardHeader>
          <CardContent className="space-y-1.5 max-h-[350px] overflow-y-auto">
            {providers.length === 0 ? (
              <EmptyState icon={<Layers className="h-7 w-7" />} title="لا يوجد مزوّدون" />
            ) : (
              providers.map((p, i) => (
                <div key={i} className="flex items-center gap-3 rounded-lg p-2.5 hover:bg-[var(--bg-hover)] transition-colors">
                  <StatusDot status={p.status} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-sm">{p.name}</span>
                      <Badge variant="outline" className="text-[10px]">{p.task}</Badge>
                    </div>
                    <div className="text-xs text-[var(--fg-muted)] mt-0.5 flex gap-2 flex-wrap">
                      <span dir="ltr">
                        {formatNumber(p.quota_used)} / {p.quota_limit ? formatNumber(p.quota_limit) : "∞"} units
                      </span>
                      <span>·</span>
                      <span>{formatNumber(p.calls || 0)} استدعاء</span>
                      {p.last_used && (
                        <>
                          <span>·</span>
                          <span>{relativeTime(p.last_used)}</span>
                        </>
                      )}
                    </div>
                  </div>
                  <Badge variant={p.key_state === "set" ? "success" : p.key_state === "missing" ? "danger" : "default"}>
                    {p.key_state === "set" ? "مفتاح ✔" : p.key_state === "missing" ? "بدون مفتاح" : p.key_state === "local" ? "محلي" : "?"}
                  </Badge>
                </div>
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>
              <HardDrive className="h-4 w-4 text-[var(--warn)]" />
              الكاش
            </CardTitle>
            <CardDescription>3 مستويات: L1 · L2 · L3</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-3 gap-2">
              {Object.entries(cacheEntries).map(([lvl, n]) => (
                <div key={lvl} className="rounded-lg p-2.5 bg-[var(--bg-soft)] border border-[var(--border-soft)] text-center">
                  <div className="text-[10px] text-[var(--fg-soft)] mb-1">{lvl}</div>
                  <div className="text-xl font-bold tabular-nums">{formatNumber(n)}</div>
                </div>
              ))}
            </div>
            <div className="rounded-lg p-3 bg-[var(--bg-soft)] border border-[var(--border-soft)]">
              <div className="text-xs text-[var(--fg-soft)] mb-2 flex items-center gap-1.5">
                <Database className="h-3 w-3" />
                معلومات النظام
              </div>
              <div className="space-y-1.5 text-xs">
                <SysRow label="الإصدار" value={data?.version || "—"} />
                <SysRow label="Python" value={data?.system?.python || "—"} />
                <SysRow label="Supabase" value={data?.system?.supabase_configured ? "✔ مهيأ" : "✗ غير مهيأ"}
                  ok={data?.system?.supabase_configured} />
                <SysRow label="إجمالي الـleads" value={formatNumber(leadsTotal)} />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Danger zone */}
      <Card>
        <CardHeader>
          <CardTitle className="text-[var(--danger)]">
            <AlertTriangle className="h-4 w-4" />
            منطقة الخطر
          </CardTitle>
          <CardDescription>إجراءات لا يمكن التراجع عنها</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-3">
          <Button
            variant="ghost"
            onClick={async () => {
              if (!confirm("سيتم مسح الكاش فقط (L1/L2/L3). متأكد؟")) return;
              try {
                await apiPost.purgeCache();
                toast.success("تم مسح الكاش");
                refetch();
              } catch (e) {
                toast.error(friendlyError(e));
              }
            }}
          >
            <Database className="h-4 w-4" />
            مسح الكاش
          </Button>
          <Button
            variant="danger"
            onClick={async () => {
              if (!confirm("هيتم مسح كل المهام وكل العملاء المحتملين والبيانات المخزنة — مفيش رجعة بعد المسح. متأكد؟")) return;
              try {
                await apiPost.wipeData();
                toast.success("تم مسح البيانات");
                refetch();
              } catch (e) {
                toast.error(friendlyError(e));
              }
            }}
          >
            <Trash2 className="h-4 w-4" />
            مسح كل البيانات المحلية
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

// ===== Sub-components =====

function calcTrend(data: { date: string; count?: number; units?: number }[]) {
  if (!data || data.length < 2) return null;
  const today = data[data.length - 1];
  const yesterday = data[data.length - 2];
  const todayVal = today?.count ?? today?.units ?? 0;
  const yesterdayVal = yesterday?.count ?? yesterday?.units ?? 0;
  if (yesterdayVal === 0) return todayVal > 0 ? { dir: "up" as const, pct: 100 } : null;
  const pct = Math.round(((todayVal - yesterdayVal) / yesterdayVal) * 100);
  if (pct === 0) return null;
  return { dir: pct > 0 ? "up" as const : "down" as const, pct: Math.abs(pct) };
}

function MetricCard({
  icon, label, value, color, sub, trend,
}: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  color: "success" | "warn" | "info" | "danger" | "accent";
  sub?: string;
  trend?: { dir: "up" | "down"; pct: number } | null;
}) {
  const colorMap = {
    success: "var(--success)",
    warn: "var(--warn)",
    info: "var(--info)",
    danger: "var(--danger)",
    accent: "var(--accent)",
  } as const;

  return (
    <Card className="hover:border-[var(--accent)] transition-all duration-200 group relative overflow-hidden">
      <CardContent className="p-5">
        <div className="flex items-start justify-between mb-3">
          <div
            className="p-2 rounded-xl transition-transform group-hover:scale-105"
            style={{
              background: `color-mix(in srgb, ${colorMap[color]} 12%, transparent)`,
              color: colorMap[color],
            }}
          >
            {icon}
          </div>
          {trend && (
            <div
              className={cn(
                "flex items-center gap-0.5 text-xs font-semibold px-1.5 py-0.5 rounded-md",
                trend.dir === "up"
                  ? "text-[var(--success)] bg-[color-mix(in_srgb,var(--success)_12%,transparent)]"
                  : "text-[var(--danger)] bg-[color-mix(in_srgb,var(--danger)_12%,transparent)]"
              )}
            >
              {trend.dir === "up" ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
              {trend.pct}%
            </div>
          )}
        </div>
        <div className="text-2xl font-bold mb-1 tabular-nums">{value}</div>
        <div className="text-xs text-[var(--fg-muted)]">{label}</div>
        {sub && <div className="text-[10px] text-[var(--fg-soft)] mt-1">{sub}</div>}
      </CardContent>
    </Card>
  );
}

function SysRow({ label, value, ok }: { label: string; value: string; ok?: boolean }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-[var(--fg-soft)]">{label}</span>
      <span className={cn("font-medium", ok === true && "text-[var(--success)]", ok === false && "text-[var(--danger)]")}>
        {value}
      </span>
    </div>
  );
}

function JobStateBadge({ state }: { state: string }) {
  const variant =
    state === "COMPLETED" ? "success" :
    state === "RUNNING" || state === "RESUMING" ? "info" :
    state === "PAUSED" || state === "DEGRADED" ? "warn" :
    state === "FAILED" ? "danger" : "default";
  return <Badge variant={variant as any} className="text-[10px] shrink-0">{state}</Badge>;
}

function LeadsAreaChart({ data }: { data: { date: string; count: number }[] }) {
  if (!data || data.length === 0) {
    return <EmptyState icon={<TrendingUp className="h-7 w-7" />} title="لا توجد بيانات بعد" description="ستظهر هنا عند تشغيل المهام" />;
  }

  const chartData = data.map((d) => ({
    date: d.date.slice(5),
    count: d.count,
  }));

  return (
    <div className="h-[240px]">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={chartData} margin={{ top: 5, right: 5, left: -15, bottom: 0 }}>
          <defs>
            <linearGradient id="leadsGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.3} />
              <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
          <XAxis dataKey="date" stroke="var(--fg-soft)" fontSize={11} tickLine={false} axisLine={false} />
          <YAxis stroke="var(--fg-soft)" fontSize={11} tickLine={false} axisLine={false} />
          <Tooltip
            contentStyle={{
              background: "var(--bg-elev)",
              border: "1px solid var(--border)",
              borderRadius: 10,
              fontSize: 12,
              boxShadow: "var(--shadow-lg)",
            }}
            labelStyle={{ color: "var(--fg-muted)" }}
          />
          <Area
            type="monotone"
            dataKey="count"
            stroke="var(--accent)"
            strokeWidth={2}
            fill="url(#leadsGradient)"
            name="عملاء"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function ProviderHealthChart({ providers, healthy, degraded }: {
  providers: ProviderRow[];
  healthy: number;
  degraded: number;
}) {
  const disabled = providers.filter((p) => p.status === "disabled").length;
  const total = providers.length;
  const healthyPct = total > 0 ? Math.round((healthy / total) * 100) : 0;

  if (total === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>
            <Activity className="h-4 w-4 text-[var(--accent)]" />
            صحة المزوّدين
          </CardTitle>
        </CardHeader>
        <CardContent>
          <EmptyState icon={<Layers className="h-7 w-7" />} title="لا يوجد مزوّدون" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <Activity className="h-4 w-4 text-[var(--accent)]" />
          صحة المزوّدين
        </CardTitle>
        <CardDescription>{total} مزوّد إجمالي</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex items-center justify-center mb-4">
          <div className="relative h-32 w-32">
            <svg className="h-full w-full -rotate-90" viewBox="0 0 120 120">
              <circle cx="60" cy="60" r="50" fill="none" stroke="var(--bg-soft)" strokeWidth="12" />
              <circle
                cx="60" cy="60" r="50" fill="none"
                stroke="var(--success)" strokeWidth="12" strokeLinecap="round"
                strokeDasharray={`${(healthyPct / 100) * 314} 314`}
                className="transition-all duration-700"
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-2xl font-bold tabular-nums">{healthyPct}%</span>
              <span className="text-[10px] text-[var(--fg-soft)]">صحّي</span>
            </div>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-2 text-center">
          <div className="rounded-lg p-2 bg-[color-mix(in_srgb,var(--success)_8%,transparent)]">
            <div className="text-lg font-bold text-[var(--success)] tabular-nums">{healthy}</div>
            <div className="text-[10px] text-[var(--fg-soft)]">صحّي</div>
          </div>
          <div className="rounded-lg p-2 bg-[color-mix(in_srgb,var(--warn)_8%,transparent)]">
            <div className="text-lg font-bold text-[var(--warn)] tabular-nums">{degraded}</div>
            <div className="text-[10px] text-[var(--fg-soft)]">منخفض</div>
          </div>
          <div className="rounded-lg p-2 bg-[var(--bg-soft)]">
            <div className="text-lg font-bold text-[var(--fg-soft)] tabular-nums">{disabled}</div>
            <div className="text-[10px] text-[var(--fg-soft)]">معطّل</div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function UsageBarChart({ data }: { data: { provider: string; task: string; calls: number; units: number }[] }) {
  if (!data || data.length === 0) {
    return <EmptyState icon={<Cpu className="h-7 w-7" />} title="لا يوجد استهلاك بعد" />;
  }

  const chartData = data.slice(0, 8).map((d) => ({
    name: d.provider,
    units: d.units,
    calls: d.calls,
  }));

  return (
    <div className="h-[240px]">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} margin={{ top: 5, right: 5, left: -15, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
          <XAxis dataKey="name" stroke="var(--fg-soft)" fontSize={10} tickLine={false} axisLine={false} angle={-25} textAnchor="end" height={50} />
          <YAxis stroke="var(--fg-soft)" fontSize={11} tickLine={false} axisLine={false} />
          <Tooltip
            contentStyle={{
              background: "var(--bg-elev)",
              border: "1px solid var(--border)",
              borderRadius: 10,
              fontSize: 12,
              boxShadow: "var(--shadow-lg)",
            }}
            cursor={{ fill: "var(--bg-hover)", opacity: 0.5 }}
          />
          <Bar dataKey="units" radius={[6, 6, 0, 0]} name="Units">
            {chartData.map((_, i) => (
              <Cell key={i} fill="var(--accent)" fillOpacity={1 - (i * 0.08)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
