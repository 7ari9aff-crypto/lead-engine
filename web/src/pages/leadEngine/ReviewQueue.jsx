import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { useLeadEngine } from "@/lib/leadEngine/store";
import { hasContact, tr } from "@/lib/leadEngine/format";
import { PageHeader } from "@/components/leadEngine/PageHeader";
import { StatusBadge, ScoreRing, TimeAgo, EmptyState } from "@/components/leadEngine/primitives";
import { ClipboardCheck, ArrowUpRight, CheckCircle2, XCircle, FileSearch, Clock, Undo2 } from "lucide-react";

export default function ReviewQueue() {
  const { t, lang, leads, reviewLead, undoReview, researchMore, canFindContacts } = useLeadEngine();
  const navigate = useNavigate();
  const ar = lang === "ar";
  const [tab, setTab] = useState("pending");
  const [last, setLast] = useState(null); // last decision, so it can be undone

  const pending = leads.filter((l) => l.status === "READY_FOR_REVIEW" || l.status === "IN_RESEARCH")
    .sort((a, b) => b.icpFit.score - a.icpFit.score);
  const saved = leads.filter((l) => l.status === "SAVED").sort((a, b) => b.icpFit.score - a.icpFit.score);
  const queue = tab === "pending" ? pending : saved;

  const decide = (l, decision) => {
    if (reviewLead(l.id, decision)) setLast({ id: l.id, name: l.company.name, decision });
  };
  const doneLabel = { APPROVED: ar ? "اعتمدت جهة اتصال" : "Contact approved", REJECTED: ar ? "رفضت" : "Rejected", SAVED: ar ? "حفظت لوقت لاحق" : "Saved for later" };

  return (
    <>
      <PageHeader title={t("review.title")} subtitle={t("review.subtitle")} />
      <div className="px-4 lg:px-8 py-6 max-w-[1200px] space-y-4">
        <div className="flex items-center gap-1 border-b border-border" role="tablist">
          {[["pending", ar ? "بانتظار قرارك" : "Waiting for you", pending.length], ["saved", ar ? "محفوظة لوقت لاحق" : "Saved for later", saved.length]].map(([k, label, n]) => (
            <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
              className={cn("px-3 py-2 text-sm -mb-px border-b-2 transition", tab === k ? "border-foreground font-semibold" : "border-transparent text-muted-foreground hover:text-foreground")}>
              {label} <span className="tnum text-xs text-muted-foreground">({n})</span>
            </button>
          ))}
        </div>

        {last && (
          <div className="flex items-center justify-between gap-3 rounded-lg border border-border bg-secondary px-4 py-2.5 text-sm" role="status">
            <span><b>{last.name}</b> — {doneLabel[last.decision]}</span>
            <button onClick={() => { undoReview(last.id); setLast(null); }} className="inline-flex items-center gap-1.5 text-xs font-medium underline underline-offset-2">
              <Undo2 className="w-3.5 h-3.5" /> {ar ? "تراجع" : "Undo"}
            </button>
          </div>
        )}

        {queue.length === 0 ? (
          <EmptyState icon={ClipboardCheck} title={tab === "pending" ? t("empty.review") : (ar ? "لا توجد عناصر محفوظة." : "Nothing saved.")}
            hint={tab === "pending" ? (ar ? "عندما ينتهي بحث جديد ستظهر نتائجه هنا." : "Results of a finished search appear here.") : undefined}
            action={tab === "pending" ? t("common.startResearch") : undefined} onAction={() => navigate("/chat")} />
        ) : (
          <div className="space-y-3">
            {queue.map((l) => {
              const c = l.company;
              const busy = l.status === "IN_RESEARCH";
              const contactOk = hasContact(l);
              const matchCount = l.icpFit.criteria.filter((x) => x.match === "yes").length;
              const factVerified = l.facts.filter((f) => f.status === "VERIFIED").length;
              return (
                <div key={l.id} className="card-surface card-hover p-4 animate-fade-in">
                  <div className="flex flex-col lg:flex-row lg:items-center gap-4">
                    <div className="flex items-center gap-4 min-w-0 flex-1">
                      <ScoreRing score={l.icpFit.score} size={52} />
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <button onClick={() => navigate(`/leads/${l.id}`)} className="font-semibold truncate hover:underline text-start">{c.name}</button>
                          <StatusBadge status={busy ? "IN_RESEARCH" : l.verificationStatus} />
                        </div>
                        <div className="text-xs text-muted-foreground mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5">
                          <span>{tr(c.industry, lang)}</span><span>· {tr(c.location, lang)}</span>
                          <span>· {c.size} {ar ? "موظف" : "employees"}</span>
                          <span>· <TimeAgo iso={l.lastUpdated} /></span>
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-5 text-xs">
                      <Metric label={ar ? "معايير مطابقة" : "Criteria met"} value={`${matchCount}/${l.icpFit.criteria.length}`} />
                      <Metric label={ar ? "معلومات متحققة" : "Facts verified"} value={`${factVerified}/${l.facts.length}`} />
                      <Metric label={ar ? "تغطية الأدلة" : "Evidence"} value={`${l.evidenceCoverage}%`} />
                    </div>
                    <div className="flex items-center gap-2 flex-wrap lg:ms-2">
                      <button onClick={() => navigate(`/leads/${l.id}`)} className="rounded-lg border border-border px-3 py-2 text-xs font-medium hover:bg-muted transition inline-flex items-center gap-1">
                        {ar ? "التفاصيل" : "Details"} <ArrowUpRight className="w-3.5 h-3.5" />
                      </button>
                      <button disabled={busy || !contactOk} onClick={() => decide(l, "APPROVED")}
                        title={!contactOk ? (ar ? "لا توجد جهة اتصال محددة" : "No contact identified") : undefined}
                        className="h-9 px-3 rounded-lg bg-[hsl(var(--success))] text-white text-xs font-medium inline-flex items-center gap-1.5 hover:opacity-90 transition disabled:opacity-40 disabled:cursor-not-allowed">
                        <CheckCircle2 className="w-4 h-4" /> {ar ? "اعتماد" : "Approve"}
                      </button>
                      <button disabled={busy} onClick={() => decide(l, "REJECTED")}
                        className="h-9 px-3 rounded-lg bg-[hsl(var(--danger))] text-white text-xs font-medium inline-flex items-center gap-1.5 hover:opacity-90 transition disabled:opacity-40">
                        <XCircle className="w-4 h-4" /> {t("review.reject")}
                      </button>
                      <button disabled={busy} onClick={() => researchMore(l.id)} aria-label={t("review.researchMore")} title={t("review.researchMore")}
                        className="h-9 w-9 grid place-items-center rounded-lg border border-border hover:bg-muted transition disabled:opacity-40"><FileSearch className="w-4 h-4" /></button>
                      {tab === "pending" && (
                        <button disabled={busy} onClick={() => decide(l, "SAVED")} aria-label={t("review.saveLater")} title={t("review.saveLater")}
                          className="h-9 w-9 grid place-items-center rounded-lg border border-border hover:bg-muted transition disabled:opacity-40"><Clock className="w-4 h-4" /></button>
                      )}
                    </div>
                  </div>
                  {!contactOk && !busy && (
                    <p className="text-[11px] text-muted-foreground mt-3 ps-1">{canFindContacts ? (ar ? "لم تُحدَّد جهة اتصال بعد — اضغط «ابحث أكثر» ليبحث النظام عن صانع قرار." : "No contact yet — use Research more to look for a decision maker.") : (ar ? "لم تُحدَّد جهة اتصال. اربط ZoomInfo من «بيانات الاعتماد» ثم اضغط «ابحث أكثر»." : "No contact yet. Connect ZoomInfo under Credentials, then use Research more.")}</p>
                  )}
                  {busy && <p className="text-[11px] text-muted-foreground mt-3 ps-1">{ar ? "جارٍ البحث عن المعلومات الناقصة…" : "Looking for the missing information…"}</p>}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}

function Metric({ label, value }) {
  return (
    <div className="text-center">
      <div className="font-display font-semibold tnum text-sm">{value}</div>
      <div className="text-[10px] text-muted-foreground">{label}</div>
    </div>
  );
}
