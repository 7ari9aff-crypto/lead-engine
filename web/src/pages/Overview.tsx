import { useQuery } from "@tanstack/react-query";
import {
  Users,
  Briefcase,
  Activity,
  CheckCircle2,
  AlertTriangle,
  Database,
  TrendingUp,
  Sparkles,
  Trash2,
  Layers,
  Cpu,
  Database as DatabaseIcon,
  HardDrive,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Badge, StatusDot } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Spinner, EmptyState } from "@/components/ui/EmptyState";
import { apiGet, apiPost, type ProviderRow } from "@/lib/api";
import { formatNumber, relativeTime, truncate } from "@/lib/utils";
import { toast } from "sonner";

export function OverviewPage() {
  const { data, isLoading, refetch } = useQuery({
    queryKey: ["status"],
    queryFn: apiGet.status,
    refetchInterval: 5000,
  });

  if (isLoading && !data) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <Spinner className="h-8 w-8 text-[var(--accent)]" />
      </div>
    );
  }

  const providers = data?.providers ?? [];
  const recentJobs = data?.recent_jobs ?? [];
  const usage = data?.usage_totals ?? [];
  const leadsByStage = data?.leads_by_stage ?? {};
  const cacheEntries = data?.cache_entries ?? {};
  const jobsByState = data?.jobs_by_state ?? {};

  const leadsAccepted = leadsByStage.ACCEPTED || 0;
  const leadsReview = leadsByStage.REVIEW || 0;
  const leadsRejected = leadsByStage.REJECTED || 0;
  const leadsTotal = data?.leads_total ?? 0;

  const totalCost = providers.reduce((sum, p) => sum + (p.quota_used || 0), 0);
  const healthy = providers.filter((p) => p.status === "active").length;
  const degraded = providers.filter((p) => ["degraded", "exhausted", "cooldown", "disabled"].includes(p.status)).length;
  const running = jobsByState.RUNNING || 0;
  const queued = jobsByState.QUEUED || 0;
  const paused = jobsByState.PAUSED || 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Sparkles className="h-5 w-5 text-[var(--accent)]" />
          نظرة عامة على النظام
        </h1>
        <p className="text-sm text-[var(--fg-muted)] mt-1">
          حالة المحرك في الوقت الفعلي — كل الأرقام مباشرة من قاعدة البيانات.
        </p>
      </div>

      {/* Hero metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard
          icon={<CheckCircle2 className="h-5 w-5" />}
          label="Leads مقبولة"
          value={formatNumber(leadsAccepted)}
          color="success"
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
          icon={<Database className="h-5 w-5" />}
          label="استهلاك الـunits"
          value={formatNumber(totalCost)}
          color="accent"
        />
      </div>

      {/* Real charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ProviderStatusChart providers={providers} />
        <LeadsDistributionChart leadsByStage={leadsByStage} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card>
          <CardHeader>
            <CardTitle>
              <Activity className="h-4 w-4 text-[var(--accent)]" />
              صحة المزوّدين
            </CardTitle>
            <CardDescription>
              {healthy} صحّي · {degraded} منخفض · {providers.length} إجمالي
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 max-h-[400px] overflow-y-auto">
            {providers.length === 0 ? (
              <EmptyState icon={<Layers className="h-8 w-8" />} title="لا يوجد مزوّدون" />
            ) : (
              providers.map((p, i) => (
                <div
                  key={i}
                  className="flex items-center gap-3 rounded-lg p-2.5 hover:bg-[var(--bg-hover)] transition-colors"
                >
                  <StatusDot status={p.status} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-sm">{p.name}</span>
                      <Badge variant="outline" className="text-[10px]">
                        {p.task}
                      </Badge>
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
              <Briefcase className="h-4 w-4 text-[var(--info)]" />
              آخر المهام
            </CardTitle>
            <CardDescription>أحدث {Math.min(8, recentJobs.length)} مهمة</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 max-h-[400px] overflow-y-auto">
            {recentJobs.length === 0 ? (
              <EmptyState icon={<Briefcase className="h-8 w-8" />} title="لا توجد مهام بعد" />
            ) : (
              recentJobs.slice(0, 8).map((j) => (
                <div
                  key={j.job_id}
                  className="rounded-lg p-2.5 hover:bg-[var(--bg-hover)] transition-colors"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <StatusDot status={j.state} />
                      <span className="font-medium text-sm truncate" dir="ltr">
                        {truncate(j.job_id, 16)}
                      </span>
                      <Badge variant="outline" className="text-[10px]">
                        {j.icp_id}
                      </Badge>
                    </div>
                    <Badge
                      variant={
                        j.state === "COMPLETED"
                          ? "success"
                          : j.state === "RUNNING" || j.state === "RESUMING"
                          ? "info"
                          : j.state === "PAUSED" || j.state === "DEGRADED"
                          ? "warn"
                          : j.state === "FAILED"
                          ? "danger"
                          : "default"
                      }
                    >
                      {j.state}
                    </Badge>
                  </div>
                  <div className="text-xs text-[var(--fg-muted)] mt-1 flex gap-2 flex-wrap">
                    {j.created_at && <span>بدأت {relativeTime(j.created_at)}</span>}
                    {j.pause_reason && (
                      <span className="text-[var(--warn)]">· {truncate(j.pause_reason, 50)}</span>
                    )}
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>
              <HardDrive className="h-4 w-4 text-[var(--warn)]" />
              الكاش + أعلى استهلاك
            </CardTitle>
            <CardDescription>3 مستويات: L1 request · L2 entity · L3 evidence</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-3 gap-2 text-xs">
              {Object.entries(cacheEntries).map(([lvl, n]) => (
                <div key={lvl} className="rounded-lg p-2.5 bg-[var(--bg-soft)] border border-[var(--border-soft)]">
                  <div className="text-[10px] text-[var(--fg-soft)]">{lvl}</div>
                  <div className="text-lg font-bold tabular-nums">{formatNumber(n)}</div>
                </div>
              ))}
            </div>
            <div className="space-y-1.5">
              <div className="text-xs text-[var(--fg-soft)] flex items-center gap-1.5">
                <Cpu className="h-3 w-3" />
                أعلى المزوّدين استهلاكًا
              </div>
              {usage.slice(0, 5).map((u, i) => (
                <div key={i} className="flex items-center gap-2 text-xs">
                  <span className="font-medium">{u.provider}</span>
                  <span className="text-[var(--fg-soft)]">{u.task}</span>
                  <span className="ms-auto tabular-nums">{formatNumber(u.units)}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* System info */}
      <Card>
        <CardHeader>
          <CardTitle>معلومات النظام</CardTitle>
          <CardDescription>إصدار {data?.version} · Python {data?.system?.python}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3 text-xs">
            <Field label="قاعدة البيانات" value={data?.system?.db_path} mono />
            <Field
              label="Supabase"
              value={data?.system?.supabase_configured ? "✔ مهيأ" : "✗ غير مهيأ"}
              ok={data?.system?.supabase_configured}
            />
            <Field label="إجمالي leads" value={formatNumber(leadsTotal)} />
            <Field label="إجمالي الاستدعاءات" value={formatNumber(providers.reduce((s, p) => s + (p.calls || 0), 0))} />
          </div>
        </CardContent>
      </Card>

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
              } catch (e: any) {
                toast.error("فشل: " + e.message);
              }
            }}
          >
            <Database className="h-4 w-4" />
            مسح الكاش
          </Button>
          <Button
            variant="danger"
            onClick={async () => {
              if (!confirm("سيتم مسح المهام والـleads والكاش وسجل الاستهلاك — لا رجعة فيه. متأكد؟")) return;
              try {
                await apiPost.wipeData();
                toast.success("تم مسح البيانات");
                refetch();
              } catch (e: any) {
                toast.error("فشل: " + e.message);
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

function MetricCard({
  icon,
  label,
  value,
  color,
  sub,
}: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  color: "success" | "warn" | "info" | "danger" | "accent";
  sub?: string;
}) {
  const colorMap = {
    success: "var(--success)",
    warn: "var(--warn)",
    info: "var(--info)",
    danger: "var(--danger)",
    accent: "var(--accent)",
  } as const;
  return (
    <Card className="hover:border-[var(--accent)] transition-colors group">
      <CardContent className="p-5">
        <div className="flex items-start justify-between mb-3">
          <div
            className="p-2 rounded-lg"
            style={{
              background: `color-mix(in srgb, ${colorMap[color]} 15%, transparent)`,
              color: colorMap[color],
            }}
          >
            {icon}
          </div>
        </div>
        <div className="text-2xl font-bold mb-1 tabular-nums">{value}</div>
        <div className="text-xs text-[var(--fg-muted)]">{label}</div>
        {sub && <div className="text-[10px] text-[var(--fg-soft)] mt-1">{sub}</div>}
      </CardContent>
    </Card>
  );
}

function Field({ label, value, mono, ok }: { label: string; value: any; mono?: boolean; ok?: boolean }) {
  return (
    <div className="rounded-lg p-2.5 bg-[var(--bg-soft)] border border-[var(--border-soft)]">
      <div className="text-[10px] text-[var(--fg-soft)] mb-0.5">{label}</div>
      <div className={cn("text-sm font-medium truncate", ok === true && "text-[var(--success)]", ok === false && "text-[var(--danger)]")} dir={mono ? "ltr" : "rtl"}>
        {value}
      </div>
    </div>
  );
}

// cn helper
import { cn } from "@/lib/utils";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from "recharts";

function ProviderStatusChart({ providers }: { providers: ProviderRow[] }) {
  const data = [
    { name: "صحّي", value: providers.filter((p) => p.status === "active").length, color: "#10b981" },
    { name: "منخفض", value: providers.filter((p) => ["degraded", "exhausted", "cooldown"].includes(p.status)).length, color: "#f59e0b" },
    { name: "معطّل", value: providers.filter((p) => p.status === "disabled").length, color: "#6c7080" },
  ].filter((d) => d.value > 0);

  if (providers.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>
            <Activity className="h-4 w-4 text-[var(--accent)]" />
            توزيع المزوّدين
          </CardTitle>
        </CardHeader>
        <CardContent>
          <EmptyState icon={<Layers className="h-8 w-8" />} title="لا يوجد مزوّدون" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <Activity className="h-4 w-4 text-[var(--accent)]" />
          توزيع المزوّدين حسب الحالة
        </CardTitle>
        <CardDescription>{providers.length} مزوّد إجمالي</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-[220px]">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data}
                innerRadius={50}
                outerRadius={85}
                paddingAngle={2}
                dataKey="value"
                nameKey="name"
                stroke="none"
              >
                {data.map((entry, i) => (
                  <Cell key={i} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{
                  background: "var(--bg-elev)",
                  border: "1px solid var(--border)",
                  borderRadius: 8,
                  fontSize: 12,
                }}
              />
              <Legend
                iconType="circle"
                wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

function LeadsDistributionChart({ leadsByStage }: { leadsByStage: Record<string, number> }) {
  const data = [
    { name: "مقبولة", value: leadsByStage.ACCEPTED || 0, color: "#10b981" },
    { name: "مراجعة", value: leadsByStage.REVIEW || 0, color: "#f59e0b" },
    { name: "مرفوضة", value: leadsByStage.REJECTED || 0, color: "#ef4444" },
  ].filter((d) => d.value > 0);

  const total = data.reduce((s, d) => s + d.value, 0);

  if (total === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>
            <Database className="h-4 w-4 text-[var(--accent)]" />
            توزيع الـleads
          </CardTitle>
        </CardHeader>
        <CardContent>
          <EmptyState icon={<Database className="h-8 w-8" />} title="لا توجد leads بعد" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <Database className="h-4 w-4 text-[var(--accent)]" />
          توزيع الـleads
        </CardTitle>
        <CardDescription>{formatNumber(total)} lead إجمالي</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-[220px]">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data}
                innerRadius={50}
                outerRadius={85}
                paddingAngle={2}
                dataKey="value"
                nameKey="name"
                stroke="none"
              >
                {data.map((entry, i) => (
                  <Cell key={i} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{
                  background: "var(--bg-elev)",
                  border: "1px solid var(--border)",
                  borderRadius: 8,
                  fontSize: 12,
                }}
                formatter={(value: any, name: any) => [
                  `${formatNumber(value as number)} (${(((value as number) / total) * 100).toFixed(1)}%)`,
                  name,
                ]}
              />
              <Legend iconType="circle" wrapperStyle={{ fontSize: 12, paddingTop: 8 }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
