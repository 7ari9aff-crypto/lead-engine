import React, { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { useLeadEngine } from "@/lib/leadEngine/store";
import { tr } from "@/lib/leadEngine/format";
import { PageHeader } from "@/components/leadEngine/PageHeader";
import { StatusBadge, ScoreRing, TimeAgo, EmptyState, Pill, statusLabel } from "@/components/leadEngine/primitives";
import { Building2, Search, SlidersHorizontal } from "lucide-react";

export default function Leads() {
  const { t, lang, leads } = useLeadEngine();
  const ar = lang === "ar";
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("ALL");
  const [verification, setVerification] = useState("ALL");
  const [minFit, setMinFit] = useState(0);
  const [industry, setIndustry] = useState("ALL");
  const [showFilters, setShowFilters] = useState(false);

  const industries = useMemo(() => [...new Set(leads.map((l) => l.company.industry))], [leads]);

  const activeFilters = [status !== "ALL", verification !== "ALL", industry !== "ALL", minFit > 0].filter(Boolean).length;
  const reset = () => { setStatus("ALL"); setVerification("ALL"); setIndustry("ALL"); setMinFit(0); setQ(""); };

  const filtered = leads.filter((l) => {
    if (q && !(l.company.name.toLowerCase().includes(q.toLowerCase()) || (l.company.domain || "").includes(q.toLowerCase()) || (l.company.location || "").toLowerCase().includes(q.toLowerCase()))) return false;
    if (status !== "ALL" && l.status !== status) return false;
    if (verification !== "ALL" && l.verificationStatus !== verification) return false;
    if (industry !== "ALL" && l.company.industry !== industry) return false;
    if (l.icpFit.score < minFit) return false;
    return true;
  }).sort((a, b) => new Date(b.lastUpdated) - new Date(a.lastUpdated));

  const statusOptions = ["ALL", "READY_FOR_REVIEW", "APPROVED", "REJECTED", "SAVED", "IN_RESEARCH"];
  const verifOptions = ["ALL", "VERIFIED", "PARTIALLY_VERIFIED", "CONFLICTED"];

  return (
    <>
      <PageHeader title={t("nav.allLeads")} subtitle={ar ? "كل الشركات التي اكتشفها النظام، مع حالتها ودرجة مطابقتها." : "Every company the system found, with its status and fit."}
        actions={<span className="text-sm text-muted-foreground tnum">{filtered.length} / {leads.length}</span>} />

      <div className="px-4 lg:px-8 py-6 max-w-[1400px] space-y-4">
        {/* controls */}
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute top-1/2 -translate-y-1/2 start-3 w-4 h-4 text-muted-foreground" />
            <input dir="auto" value={q} onChange={(e) => setQ(e.target.value)} placeholder={lang === "ar" ? "بحث عام…" : "Global search…"} className="w-full h-9 ps-9 pe-3 rounded-lg border border-input bg-background text-sm focus-ring" />
          </div>
          <button onClick={() => setShowFilters((s) => !s)} className={cn("inline-flex items-center gap-1.5 px-3 h-9 rounded-lg border text-sm font-medium transition", showFilters ? "bg-primary text-primary-foreground border-primary" : "border-border hover:bg-muted")}>
            <SlidersHorizontal className="w-4 h-4" /> {t("common.filters")}{activeFilters > 0 && <span className="tnum text-[10px] rounded-full bg-foreground/15 px-1.5">{activeFilters}</span>}
          </button>
        </div>

        {showFilters && (
          <div className="card-surface p-4 grid sm:grid-cols-2 lg:grid-cols-4 gap-3 animate-scale-in">
            <Filter label={lang === "ar" ? "الحالة" : "Status"}>
              <select value={status} onChange={(e) => setStatus(e.target.value)} className="w-full h-9 px-2 rounded-lg border border-input bg-background text-sm focus-ring">
                {statusOptions.map((s) => <option key={s} value={s}>{s === "ALL" ? (ar ? "الكل" : "All") : statusLabel(s, lang)}</option>)}
              </select>
            </Filter>
            <Filter label={lang === "ar" ? "حالة التحقق" : "Verification"}>
              <select value={verification} onChange={(e) => setVerification(e.target.value)} className="w-full h-9 px-2 rounded-lg border border-input bg-background text-sm focus-ring">
                {verifOptions.map((s) => <option key={s} value={s}>{s === "ALL" ? (ar ? "الكل" : "All") : statusLabel(s, lang)}</option>)}
              </select>
            </Filter>
            <Filter label={lang === "ar" ? "القطاع" : "Industry"}>
              <select value={industry} onChange={(e) => setIndustry(e.target.value)} className="w-full h-9 px-2 rounded-lg border border-input bg-background text-sm focus-ring">
                <option value="ALL">{lang === "ar" ? "الكل" : "All"}</option>
                {industries.map((i) => <option key={i} value={i}>{i}</option>)}
              </select>
            </Filter>
            <Filter label={`${ar ? "مطابقة ICP ≥" : "ICP fit ≥"} ${minFit}%`}>
              <input dir="auto" type="range" min={0} max={100} value={minFit} onChange={(e) => setMinFit(Number(e.target.value))} className="w-full accent-[hsl(var(--primary))]" />
            </Filter>
          </div>
        )}

        {filtered.length === 0 ? (
          <EmptyState icon={Building2} title={leads.length === 0 ? t("empty.leads") : (ar ? "لا نتائج بهذه الفلاتر." : "No leads match these filters.")} hint={leads.length === 0 ? (ar ? "ابدأ بحثًا من الشات ليكتشف النظام عملاء لك." : "Start research from chat and the system finds leads for you.") : undefined} action={leads.length === 0 ? t("common.startResearch") : (ar ? "مسح الفلاتر" : "Clear filters")} onAction={leads.length === 0 ? () => navigate("/chat") : reset} />
        ) : (
          <>
            {/* desktop table */}
            <div className="hidden lg:block card-surface overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-[11px] text-muted-foreground border-b border-border bg-muted/30">
                    <th className="font-medium py-2.5 px-4 text-start">{lang === "ar" ? "الشركة" : "Company"}</th>
                    <th className="font-medium py-2.5 px-4 text-start">{lang === "ar" ? "الموقع" : "Location"}</th>
                    <th className="font-medium py-2.5 px-4 text-start">{lang === "ar" ? "القطاع" : "Industry"}</th>
                    <th className="font-medium py-2.5 px-4 text-center">{ar ? "المطابقة" : "Fit"}</th>
                    <th className="font-medium py-2.5 px-4 text-start">{lang === "ar" ? "الحالة" : "Status"}</th>
                    <th className="font-medium py-2.5 px-4 text-start">{lang === "ar" ? "التحقق" : "Verification"}</th>
                    <th className="font-medium py-2.5 px-4 text-center">{lang === "ar" ? "الأدلة" : "Evidence"}</th>
                    <th className="font-medium py-2.5 px-4 text-start">{lang === "ar" ? "آخر تحديث" : "Updated"}</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((l) => {
                    return (
                      <tr key={l.id} onClick={() => navigate(`/leads/${l.id}`)} onKeyDown={(e) => e.key === "Enter" && navigate(`/leads/${l.id}`)} tabIndex={0} className="border-b border-border/50 hover:bg-muted/30 focus:bg-muted/40 focus:outline-none cursor-pointer transition">
                        <td className="py-3 px-4">
                          <div className="font-medium">{l.company.name}</div>
                          <div className="text-[11px] text-muted-foreground">{l.company.domain}</div>
                        </td>
                        <td className="py-3 px-4 text-muted-foreground">{tr(l.company.location, lang)}</td>
                        <td className="py-3 px-4"><Pill>{tr(l.company.industry, lang)}</Pill></td>
                        <td className="py-3 px-4"><div className="flex items-center justify-center gap-2"><ScoreRing score={l.icpFit.score} size={36} /><span className="tnum font-medium">{l.icpFit.score}%</span></div></td>
                        <td className="py-3 px-4"><StatusBadge status={l.status} /></td>
                        <td className="py-3 px-4"><StatusBadge status={l.verificationStatus} /></td>
                        <td className="py-3 px-4 text-center tnum">{l.evidenceCoverage}%</td>
                        <td className="py-3 px-4"><TimeAgo iso={l.lastUpdated} /></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* mobile cards */}
            <div className="lg:hidden space-y-2.5">
              {filtered.map((l) => (
                <button key={l.id} onClick={() => navigate(`/leads/${l.id}`)} className="w-full text-start card-surface card-hover p-4">
                  <div className="flex items-center gap-3 mb-2">
                    <ScoreRing score={l.icpFit.score} size={40} />
                    <div className="min-w-0 flex-1">
                      <div className="font-medium truncate">{l.company.name}</div>
                      <div className="text-[11px] text-muted-foreground">{l.company.location} · {l.company.industry}</div>
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <StatusBadge status={l.status} />
                    <StatusBadge status={l.verificationStatus} />
                    <Pill>{lang === "ar" ? "أدلة" : "Evidence"} {l.evidenceCoverage}%</Pill>
                  </div>
                </button>
              ))}
            </div>
          </>
        )}
      </div>
    </>
  );
}

function Filter({ label, children }) {
  return (
    <div>
      <label className="block text-[11px] text-muted-foreground mb-1 font-medium">{label}</label>
      {children}
    </div>
  );
}