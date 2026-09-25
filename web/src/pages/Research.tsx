/**
 * Research jobs — the stage-1 cockpit: launch a natural-language research
 * objective, watch the agent live (SSE), and control it (cancel / resume /
 * RESEARCH_MORE resume). Everything here is a JOB, not a long request.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Play, Square, RotateCcw, Loader2, Radio, ListChecks,
  AlertTriangle, Clock, Coins, Users, ShieldAlert, CheckCircle2, Search,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Input } from "@/components/ui/Input";
import { useLiveData } from "@/hooks/useLiveData";
import { apiGet, apiPost, apiPostExtra, streamResearchProgress, type JobRow, type ResearchProgress } from "@/lib/api";
import { friendlyError } from "@/lib/friendly";
import { formatNumber } from "@/lib/utils";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState, Spinner } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { StaleBanner } from "@/components/ui/StaleBanner";
import { cn, truncate } from "@/lib/utils";
import { toast } from "sonner";

const STATE_AR: Record<string, string> = {
  QUEUED: "في الطابور", RUNNING: "تعمل", DISCOVERING: "استكشاف",
  RESEARCHING: "تحقيق عميق", VERIFYING: "تحقق", QUALIFYING: "تأهيل",
  PAUSED: "موقوفة (سعة)", WAITING_FOR_USER: "تنتظر إجابتك",
  READY_FOR_REVIEW: "جاهزة لمراجعتك", COMPLETED: "مكتملة",
  FAILED: "فاشلة", CANCELLED: "ملغاة", DEGRADED: "منخفضة الجاهزية",
};
const STOP_AR: Record<string, string> = {
  OBJECTIVE_SATISFIED: "الهدف تحقق", COVERAGE_ADEQUATE: "التغطية كافية",
  DIMINISHING_RETURNS: "عوائد متناقصة", BUDGET_EXHAUSTED: "استنفاد الموازنة",
  USER_STOPPED: "أوقفتها بنفسك", WAITING_USER_INPUT: "بانتظار المدخلات",
  NO_CAPACITY: "لا سعة",
};

const LIVE_STATES = new Set(["QUEUED", "RUNNING", "DISCOVERING", "RESEARCHING",
  "VERIFYING", "QUALIFYING", "PAUSED", "WAITING_FOR_USER", "RESUMING", "DEGRADED"]);

export function ResearchPage() {
  const { data: jobs, loading, error, refresh } = useLiveData(() => apiGet.jobs(), 5000);
  const researchJobs = useMemo(
    () => (jobs || []).filter((j) => j.icp_id === "agentic"),
    [jobs]
  );
  const [selected, setSelected] = useState<string | null>(null);
  const [objective, setObjective] = useState("");
  const [maxSearches, setMaxSearches] = useState(6);
  const [maxCandidates, setMaxCandidates] = useState(10);
  const [creating, setCreating] = useState(false);

  // keep the newest job selected once a fresh run starts
  useEffect(() => {
    if (!selected && researchJobs.length) setSelected(researchJobs[0].job_id);
  }, [researchJobs, selected]);

  async function launch() {
    if (!objective.trim()) return toast.error("اكتب هدف البحث أولًا");
    setCreating(true);
    try {
      const res = await apiPost.startResearch(objective.trim(), undefined, {
        max_searches: maxSearches,
        max_candidates: maxCandidates,
      });
      toast.success(`بدأت المهمة ${res.job_id} — تابعها حيًا تحت`);
      setObjective("");
      setSelected(res.job_id);
      refresh();
    } catch (e) {
      toast.error(friendlyError(e));
    } finally {
      setCreating(false);
    }
  }

  async function cancel(id: string) {
    try { await apiPostExtra.researchCancel(id); toast.success("أوقفت المهمة"); refresh(); }
    catch (e) { toast.error(friendlyError(e)); }
  }
  async function resume(id: string) {
    try { await apiPost.resumeJob(id); toast.success("استؤنفت المهمة"); refresh(); }
    catch (e) { toast.error(friendlyError(e)); }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        icon={<Search className="h-5 w-5" />}
        title="مهام البحث"
        description="اكتب الهدف بالعربي — الوكيل يبحث ويحقق ويوثق الحقائق بمصادرها ويتوقف عند مراجعتك"
      />

      {error && jobs && (
        <StaleBanner error={error} subject="قائمة مهام البحث" onRetry={() => void refresh()} />
      )}

      <Card>
        <CardContent className="p-4 space-y-3">
          <textarea
            value={objective}
            onChange={(e) => setObjective(e.target.value)}
            placeholder="مثال: ابحث عن شركات برمجيات B2B توظف 50 إلى 200 موظف ولديها نشاط نمو سريع"
            rows={2}
            className="w-full rounded-xl border border-[var(--border-soft)] bg-[var(--bg-soft)] px-3 py-2.5 text-[14px] leading-6 outline-none focus:border-[var(--accent)]"
          />
          <div className="flex flex-wrap items-center gap-3">
            <label className="text-[12px] text-[var(--fg-muted)] flex items-center gap-1.5">
              حد البحث <Coins className="h-3.5 w-3.5" />
              <input type="number" min={1} max={60} value={maxSearches}
                     onChange={(e) => setMaxSearches(+e.target.value || 1)}
                     className="w-16 rounded-lg border border-[var(--border-soft)] bg-[var(--bg-soft)] px-2 py-1 tnum" />
            </label>
            <label className="text-[12px] text-[var(--fg-muted)] flex items-center gap-1.5">
              حد المرشحين <Users className="h-3.5 w-3.5" />
              <input type="number" min={1} max={200} value={maxCandidates}
                     onChange={(e) => setMaxCandidates(+e.target.value || 1)}
                     className="w-20 rounded-lg border border-[var(--border-soft)] bg-[var(--bg-soft)] px-2 py-1 tnum" />
            </label>
            <Button variant="primary" onClick={launch} disabled={creating} className="ms-auto">
              {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              ابدأ البحث
            </Button>
          </div>
        </CardContent>
      </Card>

      {error && !jobs ? (
        <ErrorState error={error} onRetry={() => void refresh()} subject="مهام البحث" />
      ) : loading && !jobs ? <Spinner /> : researchJobs.length === 0 ? (
        <EmptyState icon={<Search className="h-8 w-8" />} title="لا توجد مهام بحث بعد"
                    description="ابدأ بأول هدف بحث من الفوق — كل مهمة بتوثق كل حقيقة بمصدرها." />
      ) : (
        <div className="grid lg:grid-cols-[minmax(280px,1fr)_2fr] gap-4">
          {/* job list */}
          <div className="space-y-2">
            {researchJobs.map((j) => (
              <button key={j.job_id} onClick={() => setSelected(j.job_id)}
                className={cn("w-full text-start rounded-xl border p-3 transition-colors",
                  selected === j.job_id
                    ? "border-[var(--accent)] bg-[color-mix(in_srgb,var(--accent)_8%,transparent)]"
                    : "border-[var(--border-soft)] bg-[var(--bg-elev)] hover:border-[var(--accent)]/50")}>
                <div className="flex items-center gap-2">
                  <Badge variant={LIVE_STATES.has(j.state) ? "info" : j.state === "READY_FOR_REVIEW" ? "warn" : j.state === "FAILED" || j.state === "CANCELLED" ? "danger" : "success"}>
                    {STATE_AR[j.state] || j.state}
                  </Badge>
                  <span className="ms-auto text-[10px] text-[var(--fg-soft)] tnum"><span dir="ltr">{j.job_id.slice(0, 14)}…</span></span>
                </div>
                <div className="text-[12.5px] text-[var(--fg-muted)] mt-1.5 truncate">
                  {truncate(j.pause_reason || j.icp_id, 48)}
                </div>
              </button>
            ))}
          </div>

          {selected && <ResearchJobPanel jobId={selected} onChanged={refresh}
                                         onCancel={cancel} onResume={resume} />}
        </div>
      )}
    </div>
  );
}

function ResearchJobPanel({ jobId, onChanged, onCancel, onResume }: {
  jobId: string; onChanged: () => void;
  onCancel: (id: string) => void; onResume: (id: string) => void;
}) {
  const [progress, setProgress] = useState<ResearchProgress | null>(null);
  const [connected, setConnected] = useState(false);
  const [narration, setNarration] = useState<string[]>([]);
  const abortRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    try { setProgress(await apiGet.researchProgress(jobId)); }
    catch { /* job may be transiently missing */ }
  }, [jobId]);

  useEffect(() => {
    const ctl = new AbortController();
    abortRef.current = ctl;
    setNarration([]);
    (async () => {
      try {
        await streamResearchProgress(jobId, (event, data) => {
          if (event === "progress") {
            setConnected(true);
            setProgress(data);
          } else if (event === "done") {
            setConnected(false);
          }
          if (data?.state) {
            const line = `${new Date().toLocaleTimeString("ar-EG-u-nu-latn")} — ${STATE_AR[data.state] || data.state}`;
            setNarration((n) => n[n.length - 1] === line ? n : [...n.slice(-30), line]);
          }
        }, ctl.signal);
      } catch (e) {
        setConnected(false);
      } finally {
        load(); // final authoritative snapshot when the stream closes
      }
    })();
    return () => ctl.abort();
  }, [jobId, load]);

  const p = progress;
  const live = p ? LIVE_STATES.has(p.state) : false;

  async function act(fn: () => Promise<any>, msg: string) {
    try { await fn(); toast.success(msg); await load(); onChanged(); }
    catch (e) { toast.error(friendlyError(e)); }
  }

  if (!p) return <Card><CardContent className="p-6 flex items-center gap-2 text-[13px] text-[var(--fg-muted)]">
    <Loader2 className="h-4 w-4 animate-spin" /> جارٍ جلب حالة المهمة…
  </CardContent></Card>;

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="p-4 space-y-3">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant={live ? "info" : p.state === "READY_FOR_REVIEW" ? "warn" : "success"}>
              {connected && live && <Radio className="h-3 w-3 animate-pulse inline me-1" />}
              {STATE_AR[p.state] || p.state}
            </Badge>
            {p.stop_reason && (
              <Badge variant="default">{STOP_AR[p.stop_reason] || p.stop_reason}</Badge>
            )}
            <span className="ms-auto text-[10px] text-[var(--fg-soft)] tnum">{jobId}</span>
          </div>
          {p.objective && <div className="text-[13.5px] font-medium leading-6">{p.objective}</div>}
          {p.state === "WAITING_FOR_USER" && (
            <div className="rounded-lg border border-amber-500/40 bg-amber-500/5 px-3 py-2 text-[12.5px] flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-amber-500" />
              الوكيل محتاج إجابتك — جاوبه من صفحة المحادثة ثم استأنف.
            </div>
          )}
          <div className="flex gap-2 flex-wrap">
            {live && p.state !== "PAUSED" && (
              <Button variant="outline" onClick={() => act(() => apiPostExtra.researchCancel(jobId), "أوقفت المهمة")}
                      className="text-[12px] h-8">
                <Square className="h-3.5 w-3.5" /> إيقاف
              </Button>
            )}
            {(p.state === "PAUSED" || p.state === "READY_FOR_REVIEW") && (
              <Button variant="primary" onClick={() => act(() => apiPost.resumeJob(jobId), "استؤنفت")}
                      className="text-[12px] h-8">
                <RotateCcw className="h-3.5 w-3.5" />
                {p.state === "READY_FOR_REVIEW" ? "بحث أعمق" : "استئناف"}
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {/* live narration */}
      {narration.length > 0 && (
        <Card>
          <CardContent className="p-4">
            <div className="text-[12px] font-semibold text-[var(--fg-soft)] mb-2 flex items-center gap-1.5">
              <Radio className={cn("h-3.5 w-3.5", live && "text-[var(--accent)] animate-pulse")} />
              السرد الحي
            </div>
            <div className="space-y-1 max-h-40 overflow-y-auto">
              {[...narration].reverse().map((line, i) => (
                <div key={i} className="text-[11.5px] text-[var(--fg-muted)] tnum">{line}</div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* stats + budgets */}
      <div className="grid grid-cols-3 gap-3">
        <StatMini icon={<Users className="h-4 w-4" />} label="مرشحون" value={p.stats.candidates} />
        <StatMini icon={<ListChecks className="h-4 w-4" />} label="حقائق" value={p.stats.all_facts} />
        <StatMini icon={<ShieldAlert className="h-4 w-4" />} label="تعارضات" value={p.stats.open_conflicts} />
        <StatMini icon={<CheckCircle2 className="h-4 w-4" />} label="موثقة" value={p.stats.verified_facts} />
        <StatMini icon={<Clock className="h-4 w-4" />} label="مصادر مزارة" value={p.stats.visited_sources} />
        <StatMini icon={<Coins className="h-4 w-4" />} label="عمليات بحث" value={p.counters.searches || 0} />
      </div>

      {Object.keys(p.budgets).length > 0 && (
        <Card>
          <CardContent className="p-4 space-y-2">
            <div className="text-[12px] font-semibold text-[var(--fg-soft)]">الموازنة</div>
            {Object.entries(p.budgets).map(([key, b]) => {
              const pct = b.limit ? Math.min(100, Math.round((b.used / b.limit) * 100)) : 0;
              return (
                <div key={key} className="flex items-center gap-2">
                  <span className="text-[11px] text-[var(--fg-muted)] w-28 shrink-0">{key}</span>
                  <div className="flex-1 h-2 rounded-full bg-[var(--bg-soft)] overflow-hidden">
                    <div className={cn("h-full rounded-full", pct > 90 ? "bg-rose-500" : pct > 70 ? "bg-amber-500" : "bg-[var(--accent)]")}
                         style={{ width: `${pct}%` }} />
                  </div>
                  <span className="text-[10px] text-[var(--fg-soft)] tnum w-16">{b.used}/{b.limit}</span>
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function StatMini({ icon, label, value }: { icon: React.ReactNode; label: string; value: number }) {
  return (
    <div className="rounded-xl border border-[var(--border-soft)] bg-[var(--bg-elev)] p-3">
      <div className="flex items-center gap-1.5 text-[10.5px] text-[var(--fg-soft)]">{icon}{label}</div>
      <div className="text-[18px] font-bold tnum mt-0.5">{formatNumber(value)}</div>
    </div>
  );
}
