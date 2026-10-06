import React from "react";
import { useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { useLeadEngine } from "@/lib/leadEngine/store";
import { PageHeader } from "@/components/leadEngine/PageHeader";
import { StatusBadge, StatCard, TimeAgo, Pill, TONE_BG } from "@/components/leadEngine/primitives";
import { Radar, ClipboardCheck, Server, Gauge, ArrowUpRight, AlertTriangle, Clock, MessageSquare, Activity as ActivityIcon } from "lucide-react";

const short = (s = "") => (s.length > 44 ? `${s.slice(0, 44)}…` : s);
const LIVE_STATUSES = ["DISCOVERING", "RESEARCHING", "VERIFYING", "QUALIFYING", "RUNNING"];

export default function CommandCenter() {
  const { t, lang, jobs, leads, providers, activity, currentUser } = useLeadEngine();
  const navigate = useNavigate();

  const activeJobs = jobs.filter((j) => LIVE_STATUSES.includes(j.status));
  const readyLeads = leads.filter((l) => l.status === "READY_FOR_REVIEW");
  const waitingJobs = jobs.filter((j) => j.status === "WAITING_FOR_USER");
  const pausedJobs = jobs.filter((j) => j.status === "PAUSED");
  const degradedProviders = providers.filter((p) => p.status !== "OPERATIONAL");
  const totalBudget = jobs.reduce((a, j) => a + (j.budget?.used || 0), 0);

  const actions = [
    ...readyLeads.slice(0, 3).map((l) => ({ kind: "review", text: `${l.company.name} ${lang === "ar" ? "تنتظر المراجعة" : "awaiting review"}`, to: `/leads/${l.id}`, tone: "primary" })),
    ...waitingJobs.slice(0, 2).map((j) => ({ kind: "question", text: `«${short(j.objective)}» ${lang === "ar" ? "تنتظر إجابتك" : "is waiting for your answer"}`, to: `/jobs/${j.id}`, tone: "warning" })),
    ...pausedJobs.slice(0, 2).map((j) => ({ kind: "paused", text: `«${short(j.objective)}» ${lang === "ar" ? "متوقفة مؤقتًا" : "is paused"}`, to: `/jobs/${j.id}`, tone: "warning" })),
    ...degradedProviders.slice(0, 2).map((p) => ({ kind: "provider", text: `${p.name}: ${p.health}`, to: p.status === "DISCONNECTED" ? "/credentials" : "/providers", tone: p.status === "DISCONNECTED" ? "danger" : "warning" })),
  ];

  const recent = [...jobs].sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt)).slice(0, 4);

  return (
    <>
      <PageHeader
        title={t("cc.title")}
        subtitle={t("cc.subtitle")}
        actions={
          <button onClick={() => navigate("/chat")} className="focus-ring rounded-lg bg-primary text-primary-foreground px-4 py-2 text-sm font-medium hover:opacity-90 transition inline-flex items-center gap-2">
            <MessageSquare className="w-4 h-4" /> {t("common.startResearch")}
          </button>
        }
      />

      <div className="px-4 lg:px-8 py-6 space-y-6 max-w-[1400px]">
        {/* stat row */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <StatCard label={t("cc.activeResearch")} value={activeJobs.length} sub={lang === "ar" ? "وظائف قيد التشغيل" : "jobs running"} icon={Radar} tone="info" />
          <StatCard label={t("cc.readyForReview")} value={readyLeads.length} sub={lang === "ar" ? "تنتظر قرارك" : "awaiting your decision"} icon={ClipboardCheck} tone="primary" />
          <StatCard label={t("cc.systemHealth")} value={degradedProviders.length === 0 ? (lang === "ar" ? "سليم" : "Healthy") : (lang === "ar" ? `${degradedProviders.length} يحتاج انتباهًا` : `${degradedProviders.length} need attention`)} sub={`${providers.length} ${lang === "ar" ? "مزودين" : "providers"}`} icon={Server} tone={degradedProviders.length ? "warning" : "success"} />
          <StatCard label={t("cc.usage")} value={totalBudget.toLocaleString()} sub={lang === "ar" ? `نقطة مستهلكة عبر ${jobs.length} وظائف` : `points spent across ${jobs.length} jobs`} icon={Gauge} tone="slate" />
        </div>

        <div className="grid lg:grid-cols-3 gap-6">
          {/* action center */}
          <div className="card-surface p-5 lg:col-span-2">
            <h3 className="text-sm font-semibold mb-3 flex items-center gap-2"><AlertTriangle className="w-4 h-4 text-[hsl(var(--warning))]" /> {t("cc.actionCenter")}</h3>
            {actions.length === 0 ? (
              <p className="text-sm text-muted-foreground py-4">{lang === "ar" ? "لا شيء يحتاج تدخلك الآن." : "Nothing needs your attention right now."}</p>
            ) : (
              <div className="divide-y divide-border">
                {actions.map((a, i) => (
                  <button key={i} onClick={() => navigate(a.to)} className="w-full flex items-center gap-3 py-3 text-start hover:bg-muted/40 -mx-2 px-2 rounded-lg transition group">
                    <span className={cn("w-2 h-2 rounded-full shrink-0", TONE_BG[a.tone] || TONE_BG.slate)} />
                    <span className="text-sm flex-1">{a.text}</span>
                    <ArrowUpRight className="w-4 h-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition" />
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* system health mini */}
          <div className="card-surface p-5">
            <h3 className="text-sm font-semibold mb-3">{t("cc.systemHealth")}</h3>
            <div className="space-y-2.5">
              {providers.map((p) => (
                <div key={p.id} className="flex items-center justify-between text-sm">
                  <span>{p.name}</span>
                  <Pill tone={p.status === "OPERATIONAL" ? "success" : p.status === "DISCONNECTED" ? "danger" : "warning"}>{p.health}</Pill>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* recent results */}
        <div className="card-surface p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold flex items-center gap-2"><Clock className="w-4 h-4 text-muted-foreground" /> {t("cc.recentResults")}</h3>
            <button onClick={() => navigate("/jobs")} className="text-xs text-primary hover:underline inline-flex items-center gap-1">{lang === "ar" ? "كل الوظائف" : "All jobs"} <ArrowUpRight className="w-3 h-3" /></button>
          </div>
          <div className="space-y-2">
            {recent.map((j) => {
              const last = j.stages?.readyForReview || 0;
              return (
                <button key={j.id} onClick={() => navigate(`/jobs/${j.id}`)} className="w-full flex items-center gap-4 py-2.5 hover:bg-muted/40 -mx-2 px-2 rounded-lg transition text-start">
                  <StatusBadge status={j.status} />
                  <span className="text-sm flex-1 truncate" dir="auto">{j.objective}</span>
                  <span className="text-xs text-muted-foreground hidden sm:inline tnum">{j.stages?.discovered || 0} {lang === "ar" ? "مرشح" : "cand"}</span>
                  <span className="text-xs text-muted-foreground hidden sm:inline tnum">{last} {lang === "ar" ? "جاهزة" : "ready"}</span>
                  <TimeAgo iso={j.createdAt} />
                </button>
              );
            })}
          </div>
        </div>

        {/* recent activity */}
        <div className="card-surface p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold flex items-center gap-2"><ActivityIcon className="w-4 h-4 text-muted-foreground" /> {t("nav.activity")}</h3>
            <button onClick={() => navigate("/activity")} className="text-xs text-primary hover:underline inline-flex items-center gap-1">{lang === "ar" ? "السجل الكامل" : "Full log"} <ArrowUpRight className="w-3 h-3" /></button>
          </div>
          <div className="space-y-2.5">
            {activity.slice(0, 5).map((ev) => (
              <div key={ev.id} className="flex items-start gap-3 text-sm">
                <span className="w-1.5 h-1.5 rounded-full bg-primary mt-2 shrink-0" />
                <span className="flex-1"><b>{ev.actor === "SYSTEM" ? (lang === "ar" ? "النظام" : "System") : ev.actor}</b> {ev.action} <span className="text-muted-foreground">{ev.target}</span></span>
                <TimeAgo iso={ev.at} />
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}