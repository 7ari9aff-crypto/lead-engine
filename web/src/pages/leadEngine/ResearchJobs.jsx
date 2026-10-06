import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { useLeadEngine, isLiveStatus } from "@/lib/leadEngine/store";
import { fmtNum } from "@/lib/leadEngine/format";
import { PageHeader } from "@/components/leadEngine/PageHeader";
import { StatusBadge, ProgressBar, EmptyState, TimeAgo } from "@/components/leadEngine/primitives";
import { Radar, MessageSquare, Search } from "lucide-react";

const FILTERS = [
  ["ALL", "الكل", "All"], ["RUNNING", "قيد التنفيذ", "Running"], ["WAITING_FOR_USER", "تنتظر إجابتك", "Waiting for you"],
  ["PAUSED", "متوقفة", "Paused"], ["READY_FOR_REVIEW", "جاهزة للمراجعة", "Ready for review"],
  ["COMPLETED", "مكتملة", "Completed"], ["FAILED", "فاشلة", "Failed"], ["CANCELLED", "ملغاة", "Cancelled"],
];
const matches = (j, f) => f === "ALL" || (f === "RUNNING" ? isLiveStatus(j.status) : j.status === f);

export default function ResearchJobs() {
  const { t, lang, jobs } = useLeadEngine();
  const navigate = useNavigate();
  const ar = lang === "ar";
  const [filter, setFilter] = useState("ALL");
  const [q, setQ] = useState("");

  const sorted = [...jobs].sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
  const list = sorted.filter((j) => matches(j, filter))
    .filter((j) => !q || (j.objective || "").toLowerCase().includes(q.toLowerCase()) || j.id.toLowerCase().includes(q.toLowerCase()));

  return (
    <>
      <PageHeader title={t("jobs.title")} subtitle={ar ? "كل عمليات البحث وحالتها." : "Every research run and where it stands."}
        actions={<button onClick={() => navigate("/chat")} className="focus-ring rounded-lg bg-primary text-primary-foreground px-4 py-2 text-sm font-medium hover:opacity-90 inline-flex items-center gap-2"><MessageSquare className="w-4 h-4" /> {t("common.startResearch")}</button>} />

      <div className="px-4 lg:px-8 py-6 max-w-[1300px] space-y-4">
        <div className="flex flex-col gap-3">
          <div className="relative max-w-sm w-full">
            <Search className="absolute top-1/2 -translate-y-1/2 start-3 w-4 h-4 text-muted-foreground" />
            <input dir="auto" value={q} onChange={(e) => setQ(e.target.value)} aria-label={ar ? "بحث في الوظائف" : "Search jobs"} placeholder={ar ? "ابحث في الهدف أو الرقم…" : "Search objective or ID…"} className="w-full h-9 ps-9 pe-3 rounded-lg border border-input bg-background text-sm focus-ring" />
          </div>
          <div className="flex flex-wrap gap-1.5" role="tablist">
            {FILTERS.map(([k, a, e]) => {
              const n = jobs.filter((j) => matches(j, k)).length;
              if (k !== "ALL" && n === 0 && filter !== k) return null; // no empty chips
              return (
                <button key={k} role="tab" aria-selected={filter === k} onClick={() => setFilter(k)}
                  className={cn("px-3 py-1.5 rounded-lg text-xs font-medium border transition", filter === k ? "bg-primary text-primary-foreground border-primary" : "border-border hover:bg-muted")}>
                  {ar ? a : e} <span className="tnum opacity-70">{n}</span>
                </button>
              );
            })}
          </div>
        </div>

        {list.length === 0 ? (
          <EmptyState icon={Radar} title={ar ? "لا توجد وظائف مطابقة." : "No matching jobs."} action={t("common.startResearch")} onAction={() => navigate("/chat")} />
        ) : (
          <div className="space-y-2.5">
            {list.map((j) => {
              const live = isLiveStatus(j.status);
              const s = j.stages || {};
              const budgetPct = j.budget ? Math.round((j.budget.used / j.budget.limit) * 100) : 0;
              return (
                <button key={j.id} onClick={() => navigate(`/jobs/${j.id}`)} className="w-full text-start card-surface card-hover p-4 animate-fade-in">
                  <div className="flex flex-col lg:flex-row lg:items-center gap-4">
                    <div className="flex items-center gap-3 min-w-0 flex-1">
                      <StatusBadge status={j.status} size="base" pulse={live} />
                      <div className="min-w-0">
                        <div className="text-sm font-medium truncate" dir="auto">{j.objective}</div>
                        <div className="text-xs text-muted-foreground mt-0.5 flex items-center gap-2"><span className="font-mono">{j.id}</span> · {j.createdByName} · <TimeAgo iso={j.createdAt} /></div>
                      </div>
                    </div>
                    <div className="flex items-center gap-5 text-xs">
                      <Mini label={ar ? "مكتشفة" : "Discovered"} value={fmtNum(s.discovered, lang)} />
                      <Mini label={ar ? "مؤهلة" : "Qualified"} value={fmtNum(s.qualified, lang)} />
                      <Mini label={ar ? "للمراجعة" : "For review"} value={fmtNum(s.readyForReview, lang)} />
                      <div className="w-28">
                        <div className="flex justify-between text-[10px] text-muted-foreground mb-1"><span>{t("jobs.budget")}</span><span className="tnum">{budgetPct}%</span></div>
                        <ProgressBar value={budgetPct} tone={budgetPct > 85 ? "danger" : "info"} />
                      </div>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}

function Mini({ label, value }) {
  return (
    <div className="text-center">
      <div className="font-display font-semibold tnum text-sm">{value}</div>
      <div className="text-[10px] text-muted-foreground">{label}</div>
    </div>
  );
}
