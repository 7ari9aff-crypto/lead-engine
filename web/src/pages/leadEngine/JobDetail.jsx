import React from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import { cn } from "@/lib/utils";
import { useLeadEngine, isLiveStatus } from "@/lib/leadEngine/store";
import { eventLabel } from "@/lib/leadEngine/i18n";
import { fmtDuration, fmtNum } from "@/lib/leadEngine/format";
import { PageHeader } from "@/components/leadEngine/PageHeader";
import { StatusBadge, ProgressBar, TimeAgo, Pill, ConfirmButton, TONE_BORDER_S, TONE_TEXT } from "@/components/leadEngine/primitives";
import { Clock, Server, Gauge, Ban, Play, ArrowLeft, AlertTriangle, MessageSquare } from "lucide-react";

const STOP_META = {
  COMPLETED: { ar: "اكتملت طبيعيًا", en: "Completed normally", tone: "success" },
  WAITING_FOR_USER: { ar: "تنتظر إجابتك", en: "Waiting for your answer", tone: "warning" },
  PROVIDER_UNAVAILABLE: { ar: "مزود غير متاح", en: "Provider unavailable", tone: "warning" },
  BUDGET_EXHAUSTED: { ar: "نفدت الميزانية", en: "Budget exhausted", tone: "warning" },
  POLICY_BLOCK: { ar: "أوقفتها السياسة", en: "Blocked by policy", tone: "danger" },
  SYSTEM_FAILURE: { ar: "فشل النظام", en: "System failure", tone: "danger" },
  NO_CANDIDATES: { ar: "لا مرشحين", en: "No candidates", tone: "slate" },
  CANCELLED: { ar: "أُلغيت", en: "Cancelled", tone: "slate" },
};
const STAGE_LABEL = {
  discovered: { ar: "مكتشفة", en: "Discovered" }, deduplicated: { ar: "بعد إزالة التكرار", en: "After dedup" },
  researched: { ar: "تم البحث", en: "Researched" }, verified: { ar: "تم التحقق", en: "Verified" },
  qualified: { ar: "مؤهلة", en: "Qualified" }, readyForReview: { ar: "جاهزة للمراجعة", en: "Ready for review" },
};

export default function JobDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const { t, lang, jobs, leads, icps, cancelJob, resumeJob, setActiveJobId } = useLeadEngine();
  const ar = lang === "ar";
  const job = jobs.find((j) => j.id === id);
  const back = () => (location.key === "default" ? navigate("/jobs") : navigate(-1));

  if (!job) return <div className="px-8 py-20 text-center text-muted-foreground">{ar ? "الوظيفة غير موجودة." : "Job not found."}</div>;

  const icp = icps.find((i) => i.version === job.icpVersion);
  const live = isLiveStatus(job.status);
  const cancellable = live || job.status === "PAUSED" || job.status === "WAITING_FOR_USER";
  const budgetPct = job.budget ? Math.round((job.budget.used / job.budget.limit) * 100) : 0;
  const stop = STOP_META[job.stopReason];
  const jobLeads = leads.filter((l) => l.jobId === job.id);
  const base = Math.max(job.stages?.discovered || 0, 1);
  const end = job.completedAt ? new Date(job.completedAt) : new Date();
  const duration = job.startedAt || job.createdAt ? fmtDuration(end - new Date(job.startedAt || job.createdAt), lang) : "—";
  const explain = job.pauseReason || job.failureDetail || job.waitingQuestion?.prompt;

  return (
    <>
      <PageHeader title={job.objective} subtitle={`${job.id} · ${job.createdByName}`}
        actions={
          <>
            <button onClick={back} className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="w-4 h-4" /> {ar ? "رجوع" : "Back"}</button>
            <StatusBadge status={job.status} size="base" pulse={live} />
            {job.status === "WAITING_FOR_USER" && (
              <button onClick={() => { setActiveJobId(job.id); navigate("/chat"); }} className="rounded-lg bg-primary text-primary-foreground px-3 py-1.5 text-xs font-medium hover:opacity-90 inline-flex items-center gap-1.5"><MessageSquare className="w-3.5 h-3.5" /> {ar ? "أجب في الشات" : "Answer in chat"}</button>
            )}
            {job.status === "PAUSED" && (
              <button onClick={() => resumeJob(job.id)} className="rounded-lg bg-primary text-primary-foreground px-3 py-1.5 text-xs font-medium hover:opacity-90 inline-flex items-center gap-1.5"><Play className="w-3.5 h-3.5" /> {ar ? "استئناف" : "Resume"}</button>
            )}
            {cancellable && (
              <ConfirmButton onConfirm={() => cancelJob(job.id)} confirmLabel={ar ? "تأكيد الإلغاء؟" : "Confirm cancel?"}
                className="rounded-lg border border-[hsl(var(--danger))]/40 text-[hsl(var(--danger-ink))] px-3 py-1.5 text-xs font-medium hover:bg-[hsl(var(--danger-soft))] transition inline-flex items-center gap-1.5"
                confirmClassName="rounded-lg bg-[hsl(var(--danger))] text-white px-3 py-1.5 text-xs font-medium">
                <Ban className="w-3.5 h-3.5" /> {ar ? "إلغاء الوظيفة" : "Cancel job"}
              </ConfirmButton>
            )}
          </>
        } />

      <div className="px-4 lg:px-8 py-6 max-w-[1300px] grid lg:grid-cols-[1fr_320px] gap-6">
        <div className="space-y-5 min-w-0">
          {explain && ["PAUSED", "WAITING_FOR_USER", "FAILED"].includes(job.status) && (
            <div className={cn("card-surface p-4 border-s-2 flex gap-3", TONE_BORDER_S[stop?.tone] || TONE_BORDER_S.slate)}>
              <AlertTriangle className={cn("w-5 h-5 shrink-0", TONE_TEXT[stop?.tone] || TONE_TEXT.slate)} />
              <div>
                <div className="text-sm font-semibold">{stop?.[lang]}</div>
                <p className="text-xs text-muted-foreground mt-1 leading-relaxed">{explain}</p>
              </div>
            </div>
          )}

          <section className="card-surface p-5">
            <h3 className="text-sm font-semibold mb-4">{t("jobs.stages")}</h3>
            <div className="space-y-3">
              {Object.entries(STAGE_LABEL).map(([key, lbl]) => {
                const val = job.stages?.[key] || 0;
                return (
                  <div key={key}>
                    <div className="flex justify-between text-xs mb-1"><span className="text-muted-foreground">{lbl[lang]}</span><span className="font-display font-semibold tnum">{fmtNum(val, lang)}</span></div>
                    <ProgressBar value={val} max={base} tone={key === "readyForReview" ? "success" : "primary"} />
                  </div>
                );
              })}
            </div>
          </section>

          <section className="card-surface p-5">
            <h3 className="text-sm font-semibold mb-3 flex items-center gap-2"><Clock className="w-4 h-4 text-muted-foreground" /> {t("jobs.timeline")}</h3>
            <ol className="relative ps-5 space-y-3.5">
              <span className="absolute top-1 bottom-1 start-1.5 w-px bg-border" />
              {job.timeline.map((ev, i) => (
                <li key={i} className="relative">
                  <span className="absolute -start-[18px] top-1 w-2.5 h-2.5 rounded-full bg-foreground ring-4 ring-background" />
                  <div className="flex items-center gap-2 text-sm"><span className="font-medium">{eventLabel(ev.event, lang)}</span><TimeAgo iso={ev.at} /></div>
                  {ev.detail && <p className="text-xs text-muted-foreground mt-0.5">{ev.detail}</p>}
                </li>
              ))}
            </ol>
          </section>

          <section className="card-surface p-5">
            <h3 className="text-sm font-semibold mb-3 flex items-center gap-2"><Server className="w-4 h-4 text-muted-foreground" /> {t("jobs.providers")}</h3>
            {job.providerActivity.length === 0 ? (
              <p className="text-sm text-muted-foreground">{ar ? "لا نشاط بعد." : "No activity yet."}</p>
            ) : (
              <div className="space-y-2">
                {job.providerActivity.map((p, i) => (
                  <div key={i} className="flex items-center gap-3 text-sm"><Pill>{p.provider}</Pill><span className="flex-1">{p.action}</span><TimeAgo iso={p.at} /></div>
                ))}
              </div>
            )}
          </section>

          {jobLeads.length > 0 && (
            <section className="card-surface p-5">
              <h3 className="text-sm font-semibold mb-3">{ar ? "العملاء الناتجون" : "Resulting leads"} ({jobLeads.length})</h3>
              <div className="space-y-1">
                {jobLeads.map((l) => (
                  <button key={l.id} onClick={() => navigate(`/leads/${l.id}`)} className="w-full flex items-center gap-3 py-2 hover:bg-muted/40 -mx-2 px-2 rounded-lg transition text-start text-sm">
                    <StatusBadge status={l.status} /><span className="flex-1 truncate">{l.company.name}</span><span className="text-xs text-muted-foreground tnum">ICP {l.icpFit.score}%</span>
                  </button>
                ))}
              </div>
            </section>
          )}
        </div>

        <div className="space-y-5">
          <section className="card-surface p-5">
            <h3 className="text-sm font-semibold mb-3 flex items-center gap-2"><Gauge className="w-4 h-4 text-muted-foreground" /> {t("jobs.budget")}</h3>
            <div className="flex justify-between text-sm mb-1.5"><span className="text-muted-foreground">{ar ? "المستخدم" : "Used"}</span><span className="font-display font-semibold tnum">{fmtNum(job.budget?.used, lang)} / {fmtNum(job.budget?.limit, lang)} {ar ? "نقطة" : "pts"}</span></div>
            <ProgressBar value={budgetPct} tone={budgetPct > 85 ? "danger" : "info"} />
            <div className="mt-3 pt-3 border-t border-border text-xs space-y-1.5">
              <div className="flex justify-between"><span className="text-muted-foreground">{ar ? "أُنشئت" : "Created"}</span><TimeAgo iso={job.createdAt} /></div>
              {job.completedAt && <div className="flex justify-between"><span className="text-muted-foreground">{ar ? "انتهت" : "Ended"}</span><TimeAgo iso={job.completedAt} /></div>}
              <div className="flex justify-between"><span className="text-muted-foreground">{ar ? (job.completedAt ? "المدة" : "منذ البدء") : (job.completedAt ? "Duration" : "Elapsed")}</span><span className="tnum">{duration}</span></div>
            </div>
          </section>

          <section className="card-surface p-5">
            <h3 className="text-sm font-semibold mb-3">{t("jobs.stopReason")}</h3>
            {stop ? <Pill tone={stop.tone}>{stop[lang]}</Pill> : <span className="text-sm text-muted-foreground">{ar ? "لم تتوقف — الوظيفة تعمل." : "Not stopped — still running."}</span>}
            {icp && <div className="mt-3 pt-3 border-t border-border text-xs"><span className="text-muted-foreground">{ar ? "نسخة ICP" : "ICP version"}: </span><button onClick={() => navigate("/icp")} className="underline underline-offset-2">{icp.label}</button></div>}
          </section>
        </div>
      </div>
    </>
  );
}
