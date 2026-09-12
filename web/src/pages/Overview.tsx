import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  Users, Briefcase, Activity, CheckCircle2, AlertTriangle, Trash2,
  TrendingUp, TrendingDown, Zap, Database, Plug, MailCheck, KeyRound,
  PlayCircle, ListChecks, X, ArrowLeft,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { apiGet, apiPost, type ProviderRow } from "@/lib/api";
import { formatNumber, relativeTime } from "@/lib/utils";
import { friendlyError, ICP_LABELS } from "@/lib/friendly";
import { toast } from "sonner";
import { PageSkeleton } from "@/components/ui/Skeleton";
import { AreaChart, Area, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid } from "recharts";
import { cn } from "@/lib/utils";

const CHECKLIST_DONE_KEY = "leadEngine.checklistDismissed";
const PERIODS = [
  { id: 7, label: "٧ أيام" },
  { id: 30, label: "٣٠ يوم" },
  { id: 90, label: "٩٠ يوم" },
] as const;

export function OverviewPage() {
  const { data, isLoading, refetch } = useQuery({
    queryKey: ["status"],
    queryFn: apiGet.status,
    refetchInterval: 8000,
  });
  const { data: analytics } = useQuery({
    queryKey: ["analytics"],
    queryFn: apiGet.analytics,
    refetchInterval: 20000,
  });
  const { data: integrationsData } = useQuery({
    queryKey: ["integrations"],
    queryFn: apiGet.integrations,
    refetchInterval: 60000,
  });
  const [period, setPeriod] = useState<number>(30);
  const [checklistHidden, setChecklistHidden] = useState(
    () => localStorage.getItem(CHECKLIST_DONE_KEY) === "1"
  );

  const chartData = useMemo(() => {
    const rows = analytics?.leads_over_time ?? [];
    return rows.slice(-period).map((d) => ({ date: d.date.slice(5), count: d.count }));
  }, [analytics, period]);

  if (isLoading && !data) return <PageSkeleton />;

  const providers: ProviderRow[] = data?.providers ?? [];
  const recentJobs = data?.recent_jobs ?? [];
  const leadsByStage = data?.leads_by_stage ?? {};
  const jobsByState = data?.jobs_by_state ?? {};

  const leadsAccepted = leadsByStage.ACCEPTED || 0;
  const leadsTotal = data?.leads_total ?? 0;
  const running = jobsByState.RUNNING || 0;
  const queued = jobsByState.QUEUED || 0;
  const acceptRate = leadsTotal > 0 ? Math.round((leadsAccepted / leadsTotal) * 100) : null;

  const leadsTrend = calcTrend(analytics?.leads_over_time ?? []);

  // System health — one honest line + compact rows
  const healthy = providers.filter((p) => p.status === "active").length;
  const dbOk = Boolean(data?.system?.supabase_configured);
  const connectedIntegrations = (integrationsData?.integrations ?? []).filter((i: any) => i.connected).length;
  const emailProviders = providers.filter(
    (p) => (p.key_env ?? "").includes("HUNTER") || (p.key_env ?? "").includes("ABSTRACT")
  );
  const emailOk = emailProviders.length === 0 || emailProviders.some((p) => p.status === "active");
  const allOk = dbOk && emailOk && healthy > 0;

  // Setup checklist — compact strip
  const hasKey = providers.some((p) => p.key_state === "set" || p.key_state === "local");
  const hasJob = recentJobs.length > 0 || leadsTotal > 0;
  const hasIntegration = connectedIntegrations > 0;
  const steps = [
    { done: hasKey, label: "اربط أول مفتاح", href: "/keys", icon: KeyRound },
    { done: hasJob, label: "شغّل أول حملة", href: "/jobs", icon: PlayCircle },
    { done: leadsTotal > 0, label: "استلم أول عميل", href: "/leads", icon: Users },
    { done: hasIntegration, label: "اربط تكامل — اختياري", href: "/integrations", icon: Plug },
  ];
  const stepsDone = steps.filter((s) => s.done).length;
  const checklistComplete = stepsDone === steps.length;

  return (
    <div className="space-y-6">
      {/* Header: workspace identity + primary action */}
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-[26px] font-black tracking-tight">Lead Engine</h1>
          <p className="text-[13.5px] text-[var(--fg-muted)] mt-1">
            مساحة توليد العملاء الخاصة بك — كل الأرقام مباشرة من قاعدة البيانات.
          </p>
        </div>
        <Button variant="primary" onClick={() => window.location.assign("/jobs")}>
          <PlayCircle className="h-4 w-4" />
          تشغيل حملة جديدة
        </Button>
      </div>

      {/* Compact next actions */}
      {!checklistHidden && !checklistComplete && (
        <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-elev)] px-4 py-3 flex items-center gap-3 flex-wrap">
          <span className="flex items-center gap-1.5 text-[12.5px] font-semibold text-[var(--fg-muted)] shrink-0">
            <ListChecks className="h-4 w-4 text-[var(--accent)]" />
            خطوات البدء {stepsDone}/{steps.length}
          </span>
          <div className="flex items-center gap-1.5 flex-wrap">
            {steps.filter((s) => !s.done).map((s) => {
              const Icon = s.icon;
              return (
                <button
                  key={s.label}
                  onClick={() => window.location.assign(s.href)}
                  className="flex items-center gap-1.5 h-7 px-2.5 rounded-full border border-[var(--accent)]/40 bg-[var(--accent-soft)] text-[var(--accent-hover)] text-[11.5px] font-medium hover:border-[var(--accent)] transition-colors"
                >
                  <Icon className="h-3 w-3" />
                  {s.label}
                </button>
              );
            })}
          </div>
          <button
            onClick={() => { localStorage.setItem(CHECKLIST_DONE_KEY, "1"); setChecklistHidden(true); }}
            className="ms-auto p-1 rounded text-[var(--fg-soft)] hover:text-[var(--fg)] hover:bg-[var(--bg-hover)] transition-colors"
            title="إخفاء"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {/* The 4 KPIs that matter */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        <KpiCard
          icon={<CheckCircle2 className="h-5 w-5" />}
          label="عملاء مؤهلون"
          value={formatNumber(leadsAccepted)}
          tone="success"
          trend={leadsTrend}
        />
        <KpiCard
          icon={<Users className="h-5 w-5" />}
          label="إجمالي العملاء المحتملين"
          value={formatNumber(leadsTotal)}
          tone="accent"
        />
        <KpiCard
          icon={<Briefcase className="h-5 w-5" />}
          label="حملات نشطة"
          value={formatNumber(running + queued)}
          tone="info"
          sub={running > 0 ? `${running} تعمل الآن` : queued > 0 ? `${queued} في الطابور` : undefined}
        />
        <KpiCard
          icon={<TrendingUp className="h-5 w-5" />}
          label="معدل القبول"
          value={acceptRate != null ? `${acceptRate}%` : "—"}
          tone="warn"
          sub={leadsTotal > 0 ? `${formatNumber(leadsTotal - leadsAccepted)} تحت المراجعة أو مرفوض` : undefined}
        />
      </div>

      {/* Main activity + system health */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 items-start">
        <Card className="xl:col-span-2">
          <CardHeader>
            <div>
              <CardTitle>
                <Activity className="h-4 w-4 text-[var(--accent)]" />
                نشاط توليد العملاء
              </CardTitle>
              <CardDescription>العملاء المكتشفون عبر الوقت</CardDescription>
            </div>
            <div className="flex items-center gap-1 rounded-lg border border-[var(--border-soft)] bg-[var(--bg-soft)] p-0.5">
              {PERIODS.map((p) => (
                <button
                  key={p.id}
                  onClick={() => setPeriod(p.id)}
                  className={cn(
                    "h-7 px-2.5 rounded-md text-[11.5px] font-medium transition-colors",
                    period === p.id
                      ? "bg-[var(--bg-elev)] text-[var(--fg)] shadow-sm"
                      : "text-[var(--fg-soft)] hover:text-[var(--fg-muted)]"
                  )}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </CardHeader>
          <CardContent>
            <ActivityChart data={chartData} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>
              <span className={cn("h-2 w-2 rounded-full", allOk ? "bg-[var(--success)]" : "bg-[var(--warn)]")} />
              {allOk ? "كل الأنظمة تعمل" : "فيه حاجة تحتاج انتباه"}
            </CardTitle>
            <CardDescription>فحص سريع لحالة المنصة</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2.5">
            <HealthRow
              icon={<Database className="h-4 w-4" />}
              label="قاعدة البيانات"
              ok={dbOk}
              okText="متصلة"
              badText="غير مهيأة"
            />
            <HealthRow
              icon={<Zap className="h-4 w-4" />}
              label="المزودون"
              ok={healthy > 0}
              okText={`${healthy} من ${providers.length} نشط`}
              badText="لا يوجد مزود نشط"
            />
            <HealthRow
              icon={<MailCheck className="h-4 w-4" />}
              label="فحص البريد"
              ok={emailOk}
              okText="جاهز"
              badText="بدون مزود"
            />
            <HealthRow
              icon={<Plug className="h-4 w-4" />}
              label="التكاملات"
              ok={true}
              okText={connectedIntegrations > 0 ? `${connectedIntegrations} متصل` : "غير مربوطة — اختياري"}
              badText=""
              neutral={connectedIntegrations === 0}
            />
            <button
              onClick={() => window.location.assign("/keys")}
              className="w-full mt-1 flex items-center justify-center gap-1.5 h-9 rounded-lg border border-[var(--border)] text-[12.5px] font-medium text-[var(--fg-muted)] hover:text-[var(--fg)] hover:border-[var(--accent)] transition-colors"
            >
              إدارة المزودين والمفاتيح
              <ArrowLeft className="h-3.5 w-3.5" />
            </button>
          </CardContent>
        </Card>
      </div>

      {/* Recent campaigns */}
      <Card>
        <CardHeader>
          <CardTitle>
            <Briefcase className="h-4 w-4 text-[var(--accent)]" />
            أحدث الحملات
          </CardTitle>
          <button
            onClick={() => window.location.assign("/jobs")}
            className="text-[12.5px] font-medium text-[var(--accent)] hover:underline"
          >
            عرض الكل
          </button>
        </CardHeader>
        <CardContent className="pt-0">
          {recentJobs.length === 0 ? (
            <div className="text-center py-10">
              <p className="text-[13px] text-[var(--fg-muted)]">لا توجد حملات بعد — شغّل أول حملة من قالب جاهز.</p>
              <Button variant="outline" size="sm" className="mt-3" onClick={() => window.location.assign("/jobs")}>
                <PlayCircle className="h-3.5 w-3.5" />
                ابدأ من قوالب الحملات
              </Button>
            </div>
          ) : (
            <div className="divide-y divide-[var(--border-soft)]">
              {recentJobs.slice(0, 5).map((j: any) => (
                <button
                  key={j.job_id}
                  onClick={() => window.location.assign("/jobs")}
                  className="w-full flex items-center gap-3 py-2.5 px-1 rounded-lg hover:bg-[var(--bg-hover)] transition-colors text-right"
                >
                  <StatusDotLite state={j.state} />
                  <div className="min-w-0 flex-1">
                    <div className="text-[13.5px] font-medium truncate">
                      {ICP_LABELS[j.icp_id] ?? "حملة توليد عملاء"}
                    </div>
                    <div className="text-[11.5px] text-[var(--fg-soft)]">
                      {j.created_at ? relativeTime(j.created_at) : "—"}
                    </div>
                  </div>
                  <JobBadge state={j.state} />
                </button>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Danger zone lives here, out of the way */}
      <details className="rounded-xl border border-[var(--border)] bg-[var(--bg-elev)] overflow-hidden">
        <summary className="cursor-pointer px-4 py-3 text-[13px] font-medium text-[var(--fg-muted)] flex items-center gap-2 hover:bg-[var(--bg-hover)]">
          <AlertTriangle className="h-4 w-4 text-[var(--warn)]" />
          إجراءات حساسة — مسح البيانات
        </summary>
        <div className="px-4 pb-4 flex flex-wrap items-center gap-3">
          <Button
            variant="ghost"
            onClick={async () => {
              if (!confirm("سيتم مسح البيانات المخزنة المؤقتة فقط. متأكد؟")) return;
              try {
                await apiPost.purgeCache();
                toast.success("تم المسح");
                refetch();
              } catch (e) {
                toast.error(friendlyError(e));
              }
            }}
          >
            <Trash2 className="h-4 w-4" />
            مسح المخزن المؤقت
          </Button>
          <Button
            variant="danger"
            onClick={async () => {
              if (!confirm("هيتم مسح كل الحملات وكل العملاء المحتملين والبيانات المخزنة — مفيش رجعة بعد المسح. متأكد؟")) return;
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
            مسح كل البيانات
          </Button>
        </div>
      </details>
    </div>
  );
}

// ===== Sub-components =====

function calcTrend(data: { date: string; count?: number }[]) {
  if (!data || data.length < 2) return null;
  const mid = Math.floor(data.length / 2);
  const firstHalf = data.slice(0, mid).reduce((s, d) => s + (d.count ?? 0), 0);
  const secondHalf = data.slice(mid).reduce((s, d) => s + (d.count ?? 0), 0);
  if (firstHalf === 0) return secondHalf > 0 ? { dir: "up" as const } : null;
  const pct = Math.round(((secondHalf - firstHalf) / firstHalf) * 100);
  if (pct === 0) return null;
  return { dir: pct > 0 ? ("up" as const) : ("down" as const) };
}

function KpiCard({ icon, label, value, tone, sub, trend }: {
  icon: React.ReactNode;
  label: string;
  value: string;
  tone: "success" | "accent" | "info" | "warn";
  sub?: string;
  trend?: { dir: "up" | "down" } | null;
}) {
  const colorMap = {
    success: "var(--success)",
    accent: "var(--accent)",
    info: "var(--info)",
    warn: "var(--warn)",
  } as const;
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between mb-3">
        <span
          className="h-9 w-9 rounded-xl flex items-center justify-center"
          style={{ background: `color-mix(in srgb, ${colorMap[tone]} 10%, transparent)`, color: colorMap[tone] }}
        >
          {icon}
        </span>
        {trend && (
          <span
            className={cn(
              "flex items-center gap-0.5 text-[12px] font-semibold",
              trend.dir === "up" ? "text-[var(--success)]" : "text-[var(--danger)]"
            )}
          >
            {trend.dir === "up" ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
          </span>
        )}
      </div>
      <div className="text-[30px] font-black tnum leading-none tracking-tight">{value}</div>
      <div className="text-[12.5px] text-[var(--fg-muted)] mt-2">{label}</div>
      {sub && <div className="text-[11px] text-[var(--fg-soft)] mt-1">{sub}</div>}
    </Card>
  );
}

function HealthRow({ icon, label, ok, okText, badText, neutral }: {
  icon: React.ReactNode;
  label: string;
  ok: boolean;
  okText: string;
  badText: string;
  neutral?: boolean;
}) {
  return (
    <div className="flex items-center gap-2.5">
      <span className="text-[var(--fg-soft)]">{icon}</span>
      <span className="text-[13px] font-medium flex-1">{label}</span>
      <span
        className={cn(
          "text-[12px] font-medium flex items-center gap-1.5",
          neutral ? "text-[var(--fg-soft)]" : ok ? "text-[var(--success)]" : "text-[var(--danger)]"
        )}
      >
        <span
          className={cn(
            "h-1.5 w-1.5 rounded-full",
            neutral ? "bg-[var(--fg-soft)]" : ok ? "bg-[var(--success)]" : "bg-[var(--danger)]"
          )}
        />
        {ok || neutral ? okText : badText}
      </span>
    </div>
  );
}

function StatusDotLite({ state }: { state: string }) {
  const color =
    state === "COMPLETED" || state === "DEGRADED" ? "var(--success)" :
    state === "FAILED" ? "var(--danger)" :
    state === "PAUSED" ? "var(--warn)" : "var(--accent)";
  return <span className="h-2 w-2 rounded-full shrink-0" style={{ background: color }} />;
}

function JobBadge({ state }: { state: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    COMPLETED: { label: "مكتملة", cls: "text-[var(--success)] bg-[color-mix(in_srgb,var(--success)_10%,transparent)]" },
    DEGRADED: { label: "مكتملة", cls: "text-[var(--success)] bg-[color-mix(in_srgb,var(--success)_10%,transparent)]" },
    FAILED: { label: "فاشلة", cls: "text-[var(--danger)] bg-[color-mix(in_srgb,var(--danger)_10%,transparent)]" },
    PAUSED: { label: "موقوفة", cls: "text-[var(--warn)] bg-[color-mix(in_srgb,var(--warn)_10%,transparent)]" },
  };
  const m = map[state] ?? { label: "تعمل", cls: "text-[var(--accent)] bg-[var(--accent-soft)]" };
  return (
    <span className={cn("text-[11px] font-semibold px-2 py-0.5 rounded-md shrink-0", m.cls)}>{m.label}</span>
  );
}

function ActivityChart({ data }: { data: { date: string; count: number }[] }) {
  if (!data || data.length === 0) {
    return (
      <div className="h-[260px] flex flex-col items-center justify-center gap-2">
        <TrendingUp className="h-7 w-7 text-[var(--fg-soft)]" />
        <p className="text-[13px] text-[var(--fg-muted)]">لا توجد بيانات بعد — ستظهر هنا عند تشغيل الحملات</p>
      </div>
    );
  }
  return (
    <div className="h-[260px]">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 5, right: 5, left: -15, bottom: 0 }}>
          <defs>
            <linearGradient id="ovLeads" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.28} />
              <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
          <XAxis dataKey="date" stroke="var(--fg-soft)" fontSize={11} tickLine={false} axisLine={false} />
          <YAxis stroke="var(--fg-soft)" fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} />
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
          <Area type="monotone" dataKey="count" stroke="var(--accent)" strokeWidth={2} fill="url(#ovLeads)" name="عملاء" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
