/**
 * Analytics — the deep view over `GET /api/analytics` (30-day time series).
 *
 * Deliberately separate from Overview: Overview answers "what is happening right
 * now" (live KPIs + funnel), Analytics answers "what is the trend" (time series,
 * provider usage, throughput and quality over a selectable window). Both read the
 * same endpoints and share cache keys, so the numbers can never disagree.
 */
import { useMemo, useState } from "react";
import {
  BarChart3, TrendingUp, Database, Briefcase, Activity, Zap,
  CheckCircle2, AlertTriangle, Percent, Gauge,
} from "lucide-react";
import {
  AreaChart, Area, BarChart, Bar, LineChart, Line, ResponsiveContainer,
  XAxis, YAxis, Tooltip, CartesianGrid, Legend,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageSkeleton } from "@/components/ui/Skeleton";
import { StatCard, FilterPills } from "@/components/ui/FilterPills";
import { ErrorState } from "@/components/ui/ErrorState";
import { StaleBanner } from "@/components/ui/StaleBanner";
import { apiGet, type StatusResponse } from "@/lib/api";
import { useInstantQuery } from "@/hooks/useInstantQuery";
import { formatNumber } from "@/lib/utils";

const PERIODS = [
  { value: "7", label: "٧ أيام" },
  { value: "30", label: "٣٠ يوم" },
  { value: "90", label: "٩٠ يوم" },
];

/** Shared tooltip look so every chart in the page matches. */
const tooltipStyle = {
  background: "var(--bg-elev)",
  border: "1px solid var(--border)",
  borderRadius: 12,
  fontSize: 12,
  padding: "6px 10px",
} as const;

const axisTick = { fontSize: 11 } as const;

export function AnalyticsPage() {
  const [period, setPeriod] = useState("30");

  const { data: status, isLoading: statusLoading, error: statusError, refetch: refetchStatus } =
    useInstantQuery<StatusResponse>(
    ["status"],
    () => apiGet.status(),
    { staleTime: 5_000, refetchInterval: 30_000 }
  );
  const {
    data: analytics,
    isLoading: analyticsLoading,
    error: analyticsError,
    refetch: refetchAnalytics,
  } = useInstantQuery(
    ["analytics"],
    () => apiGet.analytics(),
    { staleTime: 60_000, refetchInterval: 60_000 }
  );

  const window = Number(period);

  const leadsSeries = useMemo(
    () =>
      (analytics?.leads_over_time ?? [])
        .slice(-window)
        .map((d) => ({ date: d.date.slice(5), leads: d.count })),
    [analytics, window]
  );

  const jobsSeries = useMemo(
    () =>
      (analytics?.jobs_over_time ?? []).slice(-window).map((d) => ({
        date: d.date.slice(5),
        completed: d.completed ?? 0,
        paused: d.paused ?? 0,
        failed: d.failed ?? 0,
      })),
    [analytics, window]
  );

  const usageSeries = useMemo(
    () =>
      (analytics?.usage_over_time ?? []).slice(-window).map((d) => ({
        date: d.date.slice(5),
        calls: d.calls ?? 0,
        units: d.units ?? 0,
      })),
    [analytics, window]
  );

  // Derived quality metrics — computed from exactly the series the charts draw.
  const totals = useMemo(() => {
    const leadsInWindow = leadsSeries.reduce((n, d) => n + d.leads, 0);
    const jobsInWindow = jobsSeries.reduce((n, d) => n + d.completed + d.paused + d.failed, 0);
    const completedInWindow = jobsSeries.reduce((n, d) => n + d.completed, 0);
    const failedInWindow = jobsSeries.reduce((n, d) => n + d.failed, 0);
    const callsInWindow = usageSeries.reduce((n, d) => n + d.calls, 0);
    return {
      leadsInWindow,
      jobsInWindow,
      completedInWindow,
      callsInWindow,
      leadsPerJob: jobsInWindow ? leadsInWindow / jobsInWindow : 0,
      successRate: jobsInWindow ? (completedInWindow / jobsInWindow) * 100 : 0,
      failureRate: jobsInWindow ? (failedInWindow / jobsInWindow) * 100 : 0,
      callsPerLead: leadsInWindow ? callsInWindow / leadsInWindow : 0,
    };
  }, [leadsSeries, jobsSeries, usageSeries]);

  // Busiest day in the window — a cheap "when does the engine actually run" signal.
  const peakDay = useMemo(
    () => leadsSeries.reduce((best, d) => (d.leads > best.leads ? d : best), { date: "—", leads: 0 }),
    [leadsSeries]
  );

  if ((statusLoading || analyticsLoading) && !analytics && !status) {
    return <PageSkeleton />;
  }

  // Every chart and every aggregate on this page derives from `analytics`.
  // If it never loaded, "لا بيانات في هذا النطاق بعد" is a lie and the KPI row
  // reads 0 — so this is a failure, not an empty window.
  if (analyticsError && !analytics) {
    return (
      <ErrorState
        error={analyticsError}
        onRetry={() => void refetchAnalytics()}
        subject="الاتجاهات الزمنية"
        className="m-4"
      />
    );
  }

  return (
    <div className="space-y-5">
      <PageHeader
        icon={<BarChart3 className="h-4 w-4 text-white" />}
        title="التحليلات"
        description="اتجاهات زمنية للعملاء والحملات واستهلاك المزودين — من نفس مصدر أرقام مركز القيادة"
        action={<FilterPills value={period} onChange={setPeriod} options={PERIODS} />}
      />

      {statusError && !status && (
        <StaleBanner
          error={statusError}
          subject="بطاقات اللقطة الحية"
          onRetry={() => void refetchStatus()}
        />
      )}

      {/* KPI row — window-scoped aggregates */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <StatCard
          label="عملاء في النطاق"
          value={formatNumber(totals.leadsInWindow)}
          detail={peakDay.leads ? `أعلى يوم: ${peakDay.date}` : undefined}
          icon={Database}
        />
        <StatCard
          label="حملات في النطاق"
          value={formatNumber(totals.jobsInWindow)}
          detail={totals.completedInWindow ? `${formatNumber(totals.completedInWindow)} مكتملة` : undefined}
          icon={Briefcase}
          tone="info"
        />
        <StatCard
          label="معدل النجاح"
          value={`${totals.successRate.toFixed(1)}%`}
          icon={CheckCircle2}
          tone={totals.successRate >= 80 ? "success" : "warn"}
        />
        <StatCard
          label="معدل الفشل"
          value={`${totals.failureRate.toFixed(1)}%`}
          icon={AlertTriangle}
          tone={totals.failureRate > 10 ? "danger" : "success"}
        />
        <StatCard
          label="عملاء لكل حملة"
          value={totals.leadsPerJob.toFixed(1)}
          icon={Percent}
          tone="accent"
        />
        <StatCard
          label="نداءات لكل عميل"
          value={totals.callsPerLead.toFixed(2)}
          detail={totals.callsInWindow ? `${formatNumber(totals.callsInWindow)} نداء` : undefined}
          icon={Gauge}
          tone="info"
        />
      </div>

      {/* Live snapshot — same cache key as the Command Center, so it cannot drift */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard
          label="إجمالي العملاء"
          value={formatNumber(status?.leads_total || 0)}
          icon={Database}
          tone="accent"
        />
        <StatCard
          label="بانتظار المراجعة"
          value={formatNumber(status?.leads_by_stage?.REVIEW || 0)}
          icon={Activity}
          tone="warn"
        />
        <StatCard
          label="عملاء مقبولون"
          value={formatNumber(status?.leads_by_stage?.ACCEPTED || 0)}
          icon={Zap}
          tone="success"
        />
        <StatCard
          label="مزودون نشطون"
          value={formatNumber((status?.providers || []).filter((p) => p.status === "active").length)}
          detail={`من ${(status?.providers || []).length}`}
          icon={TrendingUp}
          tone="info"
        />
      </div>

      {/* Leads over time */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-[var(--accent)]" />
            العملاء المحتملون عبر الزمن
          </CardTitle>
          <CardDescription>عدد العملاء المكتشفين يوميًا خلال آخر {window} يوم</CardDescription>
        </CardHeader>
        <CardContent>
          {leadsSeries.length === 0 ? (
            <EmptyChart />
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <AreaChart data={leadsSeries} margin={{ top: 6, right: 8, left: -18, bottom: 0 }}>
                <defs>
                  <linearGradient id="leadsFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.45} />
                    <stop offset="100%" stopColor="var(--accent)" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-soft)" vertical={false} />
                <XAxis dataKey="date" tick={axisTick} stroke="var(--fg-soft)" />
                <YAxis tick={axisTick} stroke="var(--fg-soft)" allowDecimals={false} />
                <Tooltip contentStyle={tooltipStyle} />
                <Area
                  type="monotone"
                  dataKey="leads"
                  name="عملاء"
                  stroke="var(--accent)"
                  strokeWidth={2}
                  fill="url(#leadsFill)"
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      <div className="grid lg:grid-cols-2 gap-4">
        {/* Jobs over time — stacked outcome breakdown */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Briefcase className="h-4 w-4 text-[var(--accent)]" />
              نتائج الحملات
            </CardTitle>
            <CardDescription>توزيع حالات الحملات يوميًا (مكتملة / متوقفة / فاشلة)</CardDescription>
          </CardHeader>
          <CardContent>
            {jobsSeries.length === 0 ? (
              <EmptyChart />
            ) : (
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={jobsSeries} margin={{ top: 6, right: 8, left: -18, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border-soft)" vertical={false} />
                  <XAxis dataKey="date" tick={axisTick} stroke="var(--fg-soft)" />
                  <YAxis tick={axisTick} stroke="var(--fg-soft)" allowDecimals={false} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Bar dataKey="completed" name="مكتملة" stackId="a" fill="#10b981" />
                  <Bar dataKey="paused" name="متوقفة" stackId="a" fill="#f59e0b" />
                  <Bar dataKey="failed" name="فاشلة" stackId="a" fill="#ef4444" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        {/* Provider usage over time */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Zap className="h-4 w-4 text-[var(--accent)]" />
              استهلاك المزودين
            </CardTitle>
            <CardDescription>عدد النداءات الخارجية يوميًا (كل المزودين مجتمعين)</CardDescription>
          </CardHeader>
          <CardContent>
            {usageSeries.length === 0 ? (
              <EmptyChart />
            ) : (
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={usageSeries} margin={{ top: 6, right: 8, left: -18, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border-soft)" vertical={false} />
                  <XAxis dataKey="date" tick={axisTick} stroke="var(--fg-soft)" />
                  <YAxis tick={axisTick} stroke="var(--fg-soft)" allowDecimals={false} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Line type="monotone" dataKey="calls" name="نداءات" stroke="var(--accent)" strokeWidth={2} dot={false} />
                  <Line
                    type="monotone"
                    dataKey="units"
                    name="وحدات"
                    stroke="#8b5cf6"
                    strokeWidth={2}
                    strokeDasharray="4 3"
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

/** Honest empty state — never render a fake flat line when there is no data. */
function EmptyChart() {
  return (
    <div className="h-[260px] flex flex-col items-center justify-center text-center gap-1.5 rounded-xl border border-dashed border-[var(--border-soft)]">
      <BarChart3 className="h-6 w-6 text-[var(--fg-soft)]" />
      <div className="text-[12.5px] text-[var(--fg-muted)]">لا بيانات في هذا النطاق بعد.</div>
      <div className="text-[11px] text-[var(--fg-soft)]">شغّل حملة واحدة وستظهر الاتجاهات هنا.</div>
    </div>
  );
}
