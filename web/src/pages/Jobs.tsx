import { useMemo, useState } from "react";
import {
  PlayCircle, RotateCcw, Database, FileText, Briefcase, Loader2,
  StopCircle, Clock, CheckCircle2, XCircle, Play,
} from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge, StatusDot } from "@/components/ui/Badge";
import { Input } from "@/components/ui/Input";
import { FilterPills } from "@/components/ui/FilterPills";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/Dialog";
import { useLiveData } from "@/hooks/useLiveData";
import { apiGet, apiPost, type JobRow } from "@/lib/api";
import { toast } from "sonner";
import { formatDate, relativeTime, truncate, cn } from "@/lib/utils";
import { Spinner, EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/layout/PageHeader";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const STATE_META: Record<string, { label: string; variant: "success" | "info" | "warn" | "danger" | "default"; filter: string }> = {
  QUEUED: { label: "في الطابور", variant: "default", filter: "active" },
  RUNNING: { label: "تعمل الآن", variant: "info", filter: "active" },
  RESUMING: { label: "تستأنف", variant: "info", filter: "active" },
  DEGRADED: { label: "مكتملة بتدهور", variant: "warn", filter: "done" },
  COMPLETED: { label: "مكتملة", variant: "success", filter: "done" },
  PAUSED: { label: "موقوفة", variant: "warn", filter: "paused" },
  FAILED: { label: "فاشلة", variant: "danger", filter: "failed" },
};

export function JobsPage() {
  const { data, loading, refresh } = useLiveData(() => apiGet.jobs(), 4000);
  const [icp, setIcp] = useState("v0_saudi_dental");
  const [running, setRunning] = useState(false);
  const [filter, setFilter] = useState("all");
  const [report, setReport] = useState<any>(null);
  const [reportOpen, setReportOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  async function run() {
    setRunning(true);
    try {
      const res = await apiPost.runBenchmark({ icp });
      toast.success(`بدأت المهمة: ${res.job_id}${res.pause_reason ? ` — ${res.pause_reason}` : ""}`);
      refresh();
    } catch (e: any) {
      toast.error("فشل التشغيل: " + e.message);
    } finally {
      setRunning(false);
    }
  }

  async function resume(id: string) {
    setBusy(id);
    try {
      await apiPost.resumeJob(id);
      toast.success("تم استئناف المهمة");
      refresh();
    } catch (e: any) {
      toast.error("فشل: " + e.message);
    } finally {
      setBusy(null);
    }
  }

  async function sync(id: string) {
    setBusy(`sync:${id}`);
    try {
      const res = await apiPost.syncSupabase(id);
      toast.success(`تمت مزامنة ${res?.synced ?? res?.n ?? 0} ليد`);
      refresh();
    } catch (e: any) {
      toast.error("فشل: " + e.message);
    } finally {
      setBusy(null);
    }
  }

  async function openReport(id: string) {
    setBusy(`report:${id}`);
    try {
      const r = await apiGet.report(id);
      setReport(r);
      setReportOpen(true);
    } catch (e: any) {
      toast.error("فشل جلب التقرير: " + e.message);
    } finally {
      setBusy(null);
    }
  }

  const jobs = data ?? [];
  const counts = useMemo(() => ({
    all: jobs.length,
    active: jobs.filter((j) => ["QUEUED", "RUNNING", "RESUMING"].includes(j.state)).length,
    paused: jobs.filter((j) => j.state === "PAUSED").length,
    done: jobs.filter((j) => ["COMPLETED", "DEGRADED"].includes(j.state)).length,
    failed: jobs.filter((j) => j.state === "FAILED").length,
  }), [jobs]);

  const filtered = jobs.filter((j) => {
    if (filter === "all") return true;
    const meta = STATE_META[j.state];
    return meta?.filter === filter;
  });

  return (
    <div className="space-y-5">
      <PageHeader
        icon={<Briefcase className="h-4 w-4 text-white" />}
        title="المهام"
        description="شغّل خط التوليد الحقيقي، تابع الحالة لحظة بلحظة، واستأنف الموقوف — والمزامنة لـSupabase تلقائية"
        action={
          <div className="flex items-center gap-2">
            <Input
              value={icp}
              onChange={(e) => setIcp(e.target.value)}
              dir="ltr"
              placeholder="v0_saudi_dental"
              className="h-8 w-44 font-mono text-xs"
            />
            <Button variant="primary" size="sm" onClick={run} loading={running}>
              <Play className="h-3.5 w-3.5" />
              تشغيل جديد
            </Button>
          </div>
        }
      />

      <div className="flex items-center gap-3 flex-wrap">
        <FilterPills
          value={filter}
          onChange={setFilter}
          options={[
            { value: "all", label: `الكل ${counts.all ? `· ${counts.all}` : ""}` },
            { value: "active", label: `نشطة ${counts.active ? `· ${counts.active}` : ""}` },
            { value: "paused", label: `موقوفة ${counts.paused ? `· ${counts.paused}` : ""}` },
            { value: "done", label: `مكتملة ${counts.done ? `· ${counts.done}` : ""}` },
            { value: "failed", label: `فاشلة ${counts.failed ? `· ${counts.failed}` : ""}` },
          ]}
        />
      </div>

      {loading && !data ? (
        <div className="flex items-center justify-center py-20">
          <Spinner className="h-6 w-6 text-[var(--accent)]" />
        </div>
      ) : filtered.length === 0 ? (
        <Card>
          <EmptyState
            icon={<Briefcase className="h-8 w-8" />}
            title={jobs.length === 0 ? "لا توجد مهام بعد" : "لا مهام في هذا الفلتر"}
            description="شغّل أول مهمة من الزر أعلى الصفحة — التشغيل حقيقي على الـAPIs، ولو الحصص خلصت المهمة تتوقف مؤقتًا برسالة واضحة مش فشل."
          />
        </Card>
      ) : (
        <div className="space-y-2">
          {filtered.map((j) => (
            <JobRowCard
              key={j.job_id}
              job={j}
              busy={busy}
              onResume={resume}
              onSync={sync}
              onReport={openReport}
            />
          ))}
        </div>
      )}

      <Dialog open={reportOpen} onOpenChange={setReportOpen}>
        <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileText className="h-4 w-4" />
              تقرير المهمة
            </DialogTitle>
            <DialogDescription className="font-mono" dir="ltr">{report?.job_id}</DialogDescription>
          </DialogHeader>
          {report?.report_markdown ? (
            <div className="md-body text-[13px] rounded-lg border border-[var(--border)] bg-[var(--bg-elev)] p-5 max-h-[65vh] overflow-auto">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{report.report_markdown}</ReactMarkdown>
            </div>
          ) : (
            <pre className="text-xs bg-[var(--bg-soft)] p-3 rounded-lg border border-[var(--border)] max-h-[60vh] overflow-auto" dir="ltr">
              {JSON.stringify(report, null, 2)}
            </pre>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function JobRowCard({ job, busy, onResume, onSync, onReport }: {
  job: JobRow;
  busy: string | null;
  onResume: (id: string) => void;
  onSync: (id: string) => void;
  onReport: (id: string) => void;
}) {
  const meta = STATE_META[job.state] ?? STATE_META.QUEUED;
  const accent =
    job.state === "COMPLETED" || job.state === "DEGRADED" ? "var(--success)" :
    job.state === "FAILED" ? "var(--danger)" :
    job.state === "PAUSED" ? "var(--warn)" : "var(--accent)";
  const live = ["RUNNING", "QUEUED", "RESUMING"].includes(job.state);

  return (
    <Card className="p-0 overflow-hidden">
      <div className="flex items-center gap-4 px-4 py-3" style={{ borderInlineStart: `3px solid ${accent}` }}>
        {/* State icon */}
        <div className="shrink-0">
          {live ? (
            <Loader2 className="h-4.5 w-4.5 animate-spin text-[var(--accent)]" />
          ) : job.state === "COMPLETED" || job.state === "DEGRADED" ? (
            <CheckCircle2 className="h-4.5 w-4.5 text-[var(--success)]" />
          ) : job.state === "FAILED" ? (
            <XCircle className="h-4.5 w-4.5 text-[var(--danger)]" />
          ) : job.state === "PAUSED" ? (
            <StopCircle className="h-4.5 w-4.5 text-[var(--warn)]" />
          ) : (
            <Clock className="h-4.5 w-4.5 text-[var(--fg-soft)]" />
          )}
        </div>

        {/* Identity */}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono text-xs font-semibold" dir="ltr">{truncate(job.job_id, 22)}</span>
            <Badge variant={meta.variant} className="text-[10px]">
              <StatusDot status={job.state} />
              {meta.label}
            </Badge>
            <Badge variant="outline" className="text-[10px]">{job.icp_id}</Badge>
          </div>
          <div className="text-[11px] text-[var(--fg-soft)] mt-1 flex items-center gap-2">
            <span>{job.created_at ? formatDate(job.created_at, false) : "—"}</span>
            {job.updated_at && <span>· آخر تحديث {relativeTime(job.updated_at)}</span>}
            {job.pause_reason && (
              <span className="text-[var(--warn)] truncate max-w-xs" title={job.pause_reason}>· {job.pause_reason}</span>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="flex gap-1 shrink-0">
          {job.state === "PAUSED" && (
            <Button size="sm" variant="outline" disabled={busy === job.job_id} onClick={() => onResume(job.job_id)}>
              <RotateCcw className="h-3.5 w-3.5" />
              استئناف
            </Button>
          )}
          {(job.state === "COMPLETED" || job.state === "DEGRADED") && (
            <Button size="sm" variant="ghost" disabled={busy === `sync:${job.job_id}`} onClick={() => onSync(job.job_id)} title="مزامنة Supabase يدويًا">
              <Database className={cn("h-3.5 w-3.5", busy === `sync:${job.job_id}` && "animate-spin")} />
              مزامنة
            </Button>
          )}
          <Button size="sm" variant="ghost" disabled={busy === `report:${job.job_id}`} onClick={() => onReport(job.job_id)}>
            <FileText className="h-3.5 w-3.5" />
            التقرير
          </Button>
        </div>
      </div>
    </Card>
  );
}
