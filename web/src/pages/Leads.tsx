import { useState, useMemo } from "react";
import {
  Database,
  Download,
  Search,
  Filter,
  ExternalLink,
  Mail,
  Phone,
  Globe,
  User,
  Building2,
  TrendingUp,
  CheckCircle2,
  AlertTriangle,
  XCircle,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge, StatusDot } from "@/components/ui/Badge";
import { Input, Select } from "@/components/ui/Input";
import { useLiveData } from "@/hooks/useLiveData";
import { apiGet } from "@/lib/api";
import { downloadFile, formatNumber, truncate, cn } from "@/lib/utils";
import { Spinner, EmptyState } from "@/components/ui/EmptyState";

export function LeadsPage() {
  const { data, loading } = useLiveData(() => apiGet.leads({ limit: 500 }), 5000);
  const [search, setSearch] = useState("");
  const [stage, setStage] = useState("");
  const [jobId, setJobId] = useState("");

  const leads = data ?? [];
  const jobs = Array.from(new Set(leads.map((l) => l.job_id).filter(Boolean))) as string[];

  const filtered = useMemo(() => {
    return leads.filter((l) => {
      if (stage && l.stage !== stage) return false;
      if (jobId && l.job_id !== jobId) return false;
      if (search) {
        const q = search.toLowerCase();
        return (
          (l.name || "").toLowerCase().includes(q) ||
          (l.city || "").toLowerCase().includes(q) ||
          (l.domain || "").toLowerCase().includes(q) ||
          (l.email || "").toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [leads, search, stage, jobId]);

  const stats = useMemo(() => {
    return {
      total: leads.length,
      accepted: leads.filter((l) => l.stage === "ACCEPTED").length,
      review: leads.filter((l) => l.stage === "REVIEW").length,
      rejected: leads.filter((l) => l.stage === "REJECTED").length,
    };
  }, [leads]);

  function exportCSV() {
    if (filtered.length === 0) return;
    const headers = [
      "name", "city", "domain", "website", "phone", "email", "email_status",
      "decision_maker", "tier", "score", "stage", "legal_status", "job_id",
    ];
    const rows = filtered.map((l) =>
      headers.map((h) => `"${String((l as any)[h] ?? "").replace(/"/g, '""')}"`).join(",")
    );
    const csv = [headers.join(","), ...rows].join("\n");
    downloadFile(`leads_${Date.now()}.csv`, csv, "text/csv;charset=utf-8");
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Database className="h-5 w-5 text-[var(--accent)]" />
            الـLeads
          </h1>
          <p className="text-sm text-[var(--fg-muted)] mt-1">
            {formatNumber(stats.total)} إجمالي · {formatNumber(stats.accepted)} مقبولة ·{" "}
            {formatNumber(stats.review)} مراجعة · {formatNumber(stats.rejected)} مرفوضة
          </p>
        </div>
        <Button variant="primary" onClick={exportCSV} disabled={filtered.length === 0}>
          <Download className="h-4 w-4" />
          تنزيل CSV ({filtered.length})
        </Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatPill icon={<CheckCircle2 className="h-4 w-4" />} label="مقبولة" value={stats.accepted} color="success" />
        <StatPill icon={<AlertTriangle className="h-4 w-4" />} label="مراجعة" value={stats.review} color="warn" />
        <StatPill icon={<XCircle className="h-4 w-4" />} label="مرفوضة" value={stats.rejected} color="danger" />
        <StatPill icon={<TrendingUp className="h-4 w-4" />} label="إجمالي" value={stats.total} color="accent" />
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="p-3 flex flex-wrap items-center gap-2">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--fg-soft)]" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="ابحث بالاسم، المدينة، الإيميل…"
              className="pe-10"
            />
          </div>
          <Select value={stage} onChange={(e) => setStage(e.target.value)} className="w-40">
            <option value="">كل المراحل</option>
            <option value="ACCEPTED">مقبولة</option>
            <option value="REVIEW">مراجعة</option>
            <option value="REJECTED">مرفوضة</option>
          </Select>
          {jobs.length > 0 && (
            <Select value={jobId} onChange={(e) => setJobId(e.target.value)} className="w-48">
              <option value="">كل المهام</option>
              {jobs.map((j) => (
                <option key={j} value={j!}>
                  {truncate(j!, 30)}
                </option>
              ))}
            </Select>
          )}
        </CardContent>
      </Card>

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          {loading && !data ? (
            <div className="flex items-center justify-center py-20">
              <Spinner className="h-6 w-6 text-[var(--accent)]" />
            </div>
          ) : filtered.length === 0 ? (
            <EmptyState
              icon={<Database className="h-8 w-8" />}
              title="لا توجد leads"
              description="شغّل مهمة من تبويب المهام لتوليد leads"
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[var(--border)] bg-[var(--bg-soft)]">
                    <th className="text-right p-3 font-semibold">الاسم</th>
                    <th className="text-right p-3 font-semibold">المدينة</th>
                    <th className="text-right p-3 font-semibold">الدومين</th>
                    <th className="text-right p-3 font-semibold">الإيميل</th>
                    <th className="text-right p-3 font-semibold">صانع القرار</th>
                    <th className="text-right p-3 font-semibold">الدرجة</th>
                    <th className="text-right p-3 font-semibold">المرحلة</th>
                    <th className="text-right p-3 font-semibold">القانوني</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((l, i) => (
                    <tr
                      key={i}
                      className="border-b border-[var(--border-soft)] hover:bg-[var(--bg-hover)] transition-colors"
                    >
                      <td className="p-3">
                        <div className="flex items-center gap-2">
                          <Building2 className="h-3.5 w-3.5 text-[var(--fg-soft)] shrink-0" />
                          <div>
                            <div className="font-medium">{l.name || "—"}</div>
                            {l.phone && (
                              <div className="text-[10px] text-[var(--fg-muted)] flex items-center gap-1" dir="ltr">
                                <Phone className="h-3 w-3" /> {l.phone}
                              </div>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="p-3 text-xs">{l.city || "—"}</td>
                      <td className="p-3">
                        {l.domain ? (
                          <a
                            href={`https://${l.domain}`}
                            target="_blank"
                            rel="noopener"
                            className="text-xs text-[var(--accent)] hover:underline flex items-center gap-1 max-w-[140px]"
                            dir="ltr"
                          >
                            <Globe className="h-3 w-3 shrink-0" />
                            {truncate(l.domain, 20)}
                            <ExternalLink className="h-2.5 w-2.5" />
                          </a>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="p-3 text-xs">
                        {l.email ? (
                          <div className="flex flex-col gap-0.5">
                            <a
                              href={`mailto:${l.email}`}
                              className="text-[var(--accent)] hover:underline flex items-center gap-1"
                              dir="ltr"
                            >
                              <Mail className="h-3 w-3" />
                              {truncate(l.email, 22)}
                            </a>
                            {l.email_status && (
                              <Badge variant={l.email_status === "DELIVERABLE" ? "success" : "warn"} className="text-[9px] w-fit">
                                {l.email_status}
                              </Badge>
                            )}
                          </div>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="p-3 text-xs">
                        {l.decision_maker ? (
                          <div className="flex items-center gap-1">
                            <User className="h-3 w-3 text-[var(--fg-soft)]" />
                            {truncate(l.decision_maker, 22)}
                          </div>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="p-3">
                        {l.score != null ? (
                          <div className="flex items-center gap-2">
                            <span className="font-bold tabular-nums text-sm">{l.score.toFixed(0)}</span>
                            {l.tier && (
                              <Badge variant="outline" className="text-[9px]">
                                {l.tier}
                              </Badge>
                            )}
                          </div>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="p-3">
                        <Badge
                          variant={l.stage === "ACCEPTED" ? "success" : l.stage === "REVIEW" ? "warn" : "danger"}
                        >
                          <StatusDot status={l.stage} />
                          {l.stage}
                        </Badge>
                      </td>
                      <td className="p-3 text-xs text-[var(--fg-muted)]">
                        {l.legal_status || "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function StatPill({
  icon,
  label,
  value,
  color,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  color: "success" | "warn" | "danger" | "accent";
}) {
  const colorMap = {
    success: "var(--success)",
    warn: "var(--warn)",
    danger: "var(--danger)",
    accent: "var(--accent)",
  };
  return (
    <div className="rounded-lg p-3 bg-[var(--bg-soft)] border border-[var(--border-soft)]">
      <div
        className="flex items-center gap-2 mb-1 text-xs"
        style={{ color: colorMap[color] }}
      >
        {icon}
        {label}
      </div>
      <div className="text-2xl font-bold tabular-nums">{formatNumber(value)}</div>
    </div>
  );
}
