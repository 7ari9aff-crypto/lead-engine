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
import { PageHeader } from "@/components/layout/PageHeader";
import { StatCard } from "@/components/ui/FilterPills";

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
      <PageHeader
        icon={<Database className="h-4 w-4 text-[var(--accent)]" />}
        title="الـLeads"
        description={`${formatNumber(stats.total)} إجمالي · ${formatNumber(stats.accepted)} مقبولة · ${formatNumber(stats.review)} مراجعة · ${formatNumber(stats.rejected)} مرفوضة`}
        action={
          <Button variant="primary" onClick={exportCSV} disabled={filtered.length === 0}>
            <Download className="h-4 w-4" />
            تنزيل CSV ({filtered.length})
          </Button>
        }
      />

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard icon={CheckCircle2} label="مقبولة" value={stats.accepted} tone="success" />
        <StatCard icon={AlertTriangle} label="مراجعة" value={stats.review} tone="warn" />
        <StatCard icon={XCircle} label="مرفوضة" value={stats.rejected} tone="danger" />
        <StatCard icon={TrendingUp} label="إجمالي" value={stats.total} tone="accent" />
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
              <table className="pro-table">
                <thead>
                  <tr>
                    <th>الاسم</th>
                    <th>المدينة</th>
                    <th>الدومين</th>
                    <th>الإيميل</th>
                    <th>صانع القرار</th>
                    <th>الدرجة</th>
                    <th>المرحلة</th>
                    <th>القانوني</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((l, i) => (
                    <tr key={i}>
                      <td>
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
                      <td className="text-xs">{l.city || "—"}</td>
                      <td>
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
                      <td className="text-xs">
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
                      <td className="text-xs">
                        {l.decision_maker ? (
                          <div className="flex items-center gap-1">
                            <User className="h-3 w-3 text-[var(--fg-soft)]" />
                            {truncate(l.decision_maker, 22)}
                          </div>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td>
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
                      <td>
                        <Badge
                          variant={l.stage === "ACCEPTED" ? "success" : l.stage === "REVIEW" ? "warn" : "danger"}
                        >
                          <StatusDot status={l.stage} />
                          {l.stage}
                        </Badge>
                      </td>
                      <td className="text-xs text-[var(--fg-muted)]">
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


