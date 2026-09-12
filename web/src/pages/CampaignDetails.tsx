import { useEffect, useState } from "react";
import { useParams, Link } from "wouter";
import {
  ArrowRight, PlayCircle, FileText, Database, Clock, Target, Loader2,
  CheckCircle2, XCircle, AlertTriangle, RefreshCw,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { apiGet, apiPost } from "@/lib/api";
import { friendlyError, ICP_LABELS } from "@/lib/friendly";
import { formatDate, relativeTime, cn } from "@/lib/utils";
import { toast } from "sonner";
import { Spinner } from "@/components/ui/EmptyState";

const STAGE_LABELS: Record<string, string> = {
  discovery: "الاكتشاف",
  dedup: "إزالة التكرار",
  hard_filter: "الفلترة الصارمة",
  qualification: "التأهيل",
  enrichment: "الإثراء",
  verification: "فحص البريد",
  legal_gate: "بوابة القوانين",
};

const EVENT_LABELS: Record<string, string> = {
  "job.started": "بدأت الحملة",
  "job.completed": "اكتملت الحملة",
  "job.paused": "توقفت مؤقتًا",
  "job.failed": "فشلت",
  "stage.done": "مرحلة اكتملت",
};

export function CampaignDetailsPage() {
  const { id } = useParams();
  const jobId = id ?? "";
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      const r = await apiGet.job(jobId);
      setData(r);
    } catch (e) {
      toast.error(friendlyError(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [jobId]);

  async function act(fn: () => Promise<unknown>, ok: string) {
    setBusy(true);
    try {
      await fn();
      toast.success(ok);
      await load();
    } catch (e) {
      toast.error(friendlyError(e));
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Spinner className="h-6 w-6 text-[var(--accent)]" />
      </div>
    );
  }

  const job = data?.job;
  const events = data?.events ?? [];
  if (!job) {
    return (
      <div className="text-center py-24">
        <p className="text-sm text-[var(--fg-muted)]">الحملة مش موجودة أو اتحذفت.</p>
        <Link href="/jobs"><Button variant="outline" size="sm" className="mt-3">رجوع للحملات</Button></Link>
      </div>
    );
  }

  let stages: Record<string, any> = {};
  try { stages = JSON.parse(job.result || "{}")?.stages ?? {}; } catch { stages = {}; }

  const stateMeta: Record<string, { label: string; cls: string }> = {
    COMPLETED: { label: "مكتملة", cls: "text-[var(--success)] bg-[color-mix(in_srgb,var(--success)_10%,transparent)]" },
    DEGRADED: { label: "مكتملة", cls: "text-[var(--success)] bg-[color-mix(in_srgb,var(--success)_10%,transparent)]" },
    FAILED: { label: "فاشلة", cls: "text-[var(--danger)] bg-[color-mix(in_srgb,var(--danger)_10%,transparent)]" },
    PAUSED: { label: "موقوفة", cls: "text-[var(--warn)] bg-[color-mix(in_srgb,var(--warn)_10%,transparent)]" },
  };
  const meta = stateMeta[job.state] ?? { label: "قيد التنفيذ", cls: "text-[var(--accent)] bg-[var(--accent-soft)]" };

  return (
    <div className="space-y-5 max-w-4xl">
      {/* Header */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <Link href="/jobs" className="inline-flex items-center gap-1 text-[12px] text-[var(--fg-muted)] hover:text-[var(--fg)] transition-colors mb-1.5">
            <ArrowRight className="h-3.5 w-3.5" />
            كل الحملات
          </Link>
          <h1 className="text-[24px] font-black flex items-center gap-2.5 flex-wrap">
            {ICP_LABELS[job.icp_id] ?? "حملة توليد عملاء"}
            <span className={cn("text-[12px] font-bold px-2.5 py-1 rounded-lg", meta.cls)}>{meta.label}</span>
          </h1>
          <p className="text-[12.5px] text-[var(--fg-soft)] mt-1 flex items-center gap-2 flex-wrap">
            <Clock className="h-3.5 w-3.5" />
            بدأت {job.created_at ? formatDate(job.created_at, true) : "—"}
            {job.updated_at && <> · آخر تحديث {relativeTime(job.updated_at)}</>}
            {job.pause_reason && <span className="text-[var(--warn)]">· {job.pause_reason}</span>}
          </p>
        </div>
        <div className="flex gap-2">
          {job.state === "PAUSED" && (
            <Button variant="primary" size="sm" disabled={busy} loading={busy}
              onClick={() => act(() => apiPost.resumeJob(job.job_id), "تم استئناف الحملة")}>
              <RefreshCw className="h-3.5 w-3.5" />
              استئناف
            </Button>
          )}
          {(job.state === "COMPLETED" || job.state === "DEGRADED") && (
            <Button variant="outline" size="sm" disabled={busy}
              onClick={() => act(() => apiPost.syncSupabase(job.job_id), "تمت المزامنة")}>
              <Database className="h-3.5 w-3.5" />
              مزامنة
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={() => window.open(`/api/report/${job.job_id}`, "_blank")}>
            <FileText className="h-3.5 w-3.5" />
            التقرير الكامل
          </Button>
        </div>
      </div>

      {/* Pipeline stages */}
      <Card>
        <CardHeader>
          <CardTitle><Target className="h-4 w-4 text-[var(--accent)]" /> مراحل الخط</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 md:grid-cols-4 gap-3 pt-0">
          {Object.entries(stages).map(([key, st]) => (
            <div key={key} className="rounded-xl border border-[var(--border-soft)] bg-[var(--bg-soft)] p-3.5">
              <div className="flex items-center gap-1.5 text-[12px] font-semibold text-[var(--fg-muted)] mb-2">
                {STAGE_LABELS[key] ?? key.replace(/_/g, " ")}
              </div>
              <div className="space-y-1">
                {Object.entries(st ?? {}).filter(([, v]) => typeof v === "number").slice(0, 4).map(([k, v]: any) => (
                  <div key={k} className="flex items-center justify-between text-[12px]">
                    <span className="text-[var(--fg-soft)]">{k.replace(/_/g, " ")}</span>
                    <span className="font-bold tnum">{v}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
          {Object.keys(stages).length === 0 && (
            <p className="text-[13px] text-[var(--fg-muted)] col-span-full py-4 text-center">
              لسه مفيش مراحل مسجلة — بتظهر أول ما تبدأ الحملة شغلها.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Events timeline */}
      <Card>
        <CardHeader>
          <CardTitle><Clock className="h-4 w-4 text-[var(--accent)]" /> الخط الزمني</CardTitle>
        </CardHeader>
        <CardContent className="pt-0">
          {events.length === 0 ? (
            <p className="text-[13px] text-[var(--fg-muted)] text-center py-6">مفيش أحداث مسجلة بعد.</p>
          ) : (
            <div className="relative space-y-0.5">
              {events.slice().reverse().map((ev: any, i: number) => {
                const kind = ev.kind || "";
                const bad = kind.includes("failed");
                const good = kind.includes("completed") || kind.includes("finished");
                const warn = kind.includes("paused");
                const Icon = bad ? XCircle : good ? CheckCircle2 : warn ? AlertTriangle : Loader2;
                return (
                  <div key={ev.id ?? i} className="flex items-center gap-3 py-2">
                    <Icon className={cn(
                      "h-4 w-4 shrink-0",
                      bad ? "text-[var(--danger)]" : good ? "text-[var(--success)]" : warn ? "text-[var(--warn)]" : "text-[var(--accent)]",
                      !bad && !good && !warn && "animate-spin"
                    )} />
                    <span className="text-[13px] font-medium">
                      {EVENT_LABELS[kind] ?? kind.replace(/[._]/g, " ")}
                    </span>
                    <span className="ms-auto text-[11.5px] text-[var(--fg-soft)] tnum shrink-0">
                      {ev.created_at ? relativeTime(ev.created_at) : ""}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
