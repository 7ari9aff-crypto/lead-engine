import { useState } from "react";
import {
  PlayCircle,
  RotateCcw,
  Database,
  FileText,
  Beaker,
  Briefcase,
  Loader2,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge, StatusDot } from "@/components/ui/Badge";
import { Input, Label } from "@/components/ui/Input";
import { Switch } from "@/components/ui/Switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/Dialog";
import { useLiveData } from "@/hooks/useLiveData";
import { apiGet, apiPost } from "@/lib/api";
import { toast } from "sonner";
import { formatDate, truncate } from "@/lib/utils";
import { Spinner, EmptyState } from "@/components/ui/EmptyState";

export function JobsPage() {
  const { data, loading, refresh } = useLiveData(() => apiGet.jobs(), 5000);
  const [icp, setIcp] = useState("v0_saudi_dental");
  const [dryRun, setDryRun] = useState(false);
  const [running, setRunning] = useState(false);
  const [report, setReport] = useState<any>(null);
  const [reportOpen, setReportOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  async function run() {
    setRunning(true);
    try {
      const res = await apiPost.runBenchmark({ icp, dry_run: dryRun });
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
      toast.success(`تمت مزامنة ${res?.synced ?? res?.n ?? 0} lead`);
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

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Briefcase className="h-5 w-5 text-[var(--accent)]" />
          المهام
        </h1>
        <p className="text-sm text-[var(--fg-muted)] mt-1">
          شغّل الـpipeline، تابع المهام، استأنف الموقوفة، وزامن مع Supabase.
        </p>
      </div>

      {/* Run form */}
      <Card>
        <CardHeader>
          <CardTitle>
            <PlayCircle className="h-4 w-4 text-[var(--accent)]" />
            تشغيل الـPipeline
          </CardTitle>
          <CardDescription>
            الافتراضي تشغيل <b>حقيقي</b> على الـAPIs. لو مفيش مفتاح مناسب، المهمة هتتوقف برسالة واضحة.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-[1fr_auto_auto] gap-3 items-end">
            <div>
              <Label>ملف الـICP</Label>
              <Input value={icp} onChange={(e) => setIcp(e.target.value)} dir="ltr" placeholder="v0_saudi_dental" />
            </div>
            <div className="flex items-center gap-2 h-10 px-3 rounded-lg border border-[var(--border)] bg-[var(--bg-soft)]">
              <Switch id="dry" checked={dryRun} onCheckedChange={setDryRun} />
              <Label htmlFor="dry" className="mb-0 flex items-center gap-1.5 cursor-pointer">
                <Beaker className="h-3.5 w-3.5" />
                وضع تجريبي
              </Label>
            </div>
            <Button variant="primary" onClick={run} loading={running}>
              <PlayCircle className="h-4 w-4" />
              تشغيل الآن
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Jobs list */}
      <Card>
        <CardContent className="p-0">
          {loading && !data ? (
            <div className="flex items-center justify-center py-20">
              <Spinner className="h-6 w-6 text-[var(--accent)]" />
            </div>
          ) : jobs.length === 0 ? (
            <EmptyState
              icon={<Briefcase className="h-8 w-8" />}
              title="لا توجد مهام"
              description="شغّل الـpipeline من النموذج أعلاه"
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[var(--border)] bg-[var(--bg-soft)]">
                    <th className="text-right p-3 font-semibold">المهمة</th>
                    <th className="text-right p-3 font-semibold">ICP</th>
                    <th className="text-right p-3 font-semibold">الحالة</th>
                    <th className="text-right p-3 font-semibold">سبب الإيقاف</th>
                    <th className="text-right p-3 font-semibold">بدأت</th>
                    <th className="text-right p-3 font-semibold">إجراءات</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((j) => (
                    <tr key={j.job_id} className="border-b border-[var(--border-soft)] hover:bg-[var(--bg-hover)] transition-colors">
                      <td className="p-3 font-mono text-xs" dir="ltr">{truncate(j.job_id, 24)}</td>
                      <td className="p-3">
                        <Badge variant="outline" className="text-[10px]">{j.icp_id}</Badge>
                      </td>
                      <td className="p-3">
                        <Badge
                          variant={
                            j.state === "COMPLETED" ? "success" :
                            j.state === "RUNNING" || j.state === "RESUMING" ? "info" :
                            j.state === "PAUSED" || j.state === "DEGRADED" ? "warn" :
                            j.state === "FAILED" ? "danger" : "default"
                          }
                        >
                          <StatusDot status={j.state} />
                          {j.state}
                        </Badge>
                      </td>
                      <td className="p-3 text-xs text-[var(--fg-muted)] max-w-xs truncate" title={j.pause_reason || ""}>
                        {j.pause_reason || "—"}
                      </td>
                      <td className="p-3 text-xs text-[var(--fg-muted)]">
                        {j.created_at ? formatDate(j.created_at, false) : "—"}
                      </td>
                      <td className="p-3">
                        <div className="flex gap-1">
                          {j.state === "PAUSED" && (
                            <Button
                              size="icon-sm"
                              variant="ghost"
                              disabled={busy === j.job_id}
                              onClick={() => resume(j.job_id)}
                              title="استئناف"
                            >
                              <RotateCcw className="h-3.5 w-3.5 text-[var(--info)]" />
                            </Button>
                          )}
                          {(j.state === "COMPLETED" || j.state === "DEGRADED") && (
                            <Button
                              size="icon-sm"
                              variant="ghost"
                              disabled={busy === `sync:${j.job_id}`}
                              onClick={() => sync(j.job_id)}
                              title="مزامنة Supabase"
                            >
                              <Database className="h-3.5 w-3.5 text-[var(--accent)]" />
                            </Button>
                          )}
                          <Button
                            size="icon-sm"
                            variant="ghost"
                            disabled={busy === `report:${j.job_id}`}
                            onClick={() => openReport(j.job_id)}
                            title="التقرير"
                          >
                            <FileText className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

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
            <pre className="text-xs bg-[var(--bg-soft)] p-4 rounded-lg border border-[var(--border)] max-h-[65vh] overflow-auto whitespace-pre-wrap leading-relaxed" dir="ltr">
              {report.report_markdown}
            </pre>
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
