import React from "react";
import { cn } from "@/lib/utils";
import { useLeadEngine } from "@/lib/leadEngine/store";
import { PageHeader } from "@/components/leadEngine/PageHeader";
import { Pill, statusLabel } from "@/components/leadEngine/primitives";
import { fmtDate } from "@/lib/leadEngine/format";
import { Target, Check, GitBranch } from "lucide-react";

export default function ICP() {
  const { t, lang, icps, jobs } = useLeadEngine();

  return (
    <>
      <PageHeader title={t("icp.title")} subtitle={lang === "ar" ? "معايير العميل المثالي على شكل نسخ. كل وظيفة بحث تعمل بنسخة محددة." : "Your ideal-customer criteria as versions. Every research job runs on one."} />
      <div className="px-4 lg:px-8 py-6 max-w-[1200px] space-y-4">
        {icps.map((icp) => {
          const usedBy = jobs.filter((j) => j.icpVersion === icp.version);
          return (
            <div key={icp.id} className={cn("card-surface p-5", icp.isCurrent && "border-s-2 border-s-[hsl(var(--primary))] bg-[hsl(var(--accent))]/20")}>
              <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 mb-4">
                <div className="flex items-center gap-3">
                  <div className={cn("w-10 h-10 rounded-lg grid place-items-center", icp.isCurrent ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground")}>
                    <Target className="w-5 h-5" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="font-semibold">{icp.label}</h3>
                      {icp.isCurrent && <Pill tone="primary">{t("icp.current")}</Pill>}
                    </div>
                    <div className="text-xs text-muted-foreground mt-0.5">{t("icp.createdBy")} {icp.createdBy} · {fmtDate(icp.createdAt, lang)}</div>
                  </div>
                </div>
                <div className="text-xs text-muted-foreground flex items-center gap-1.5">
                  <GitBranch className="w-3.5 h-3.5" /> {usedBy.length} {lang === "ar" ? "وظائف بحث" : "research jobs"}
                </div>
              </div>

              <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-2 text-sm mb-4">
                {/* Real definition shape (engine.icp_versions.definition):
                    industry is a free-text string, cities is [{name}],
                    keywords_* are arrays, criteria holds min_branches/notes.
                    The demo shape this page was written against (industry as
                    an array, flat location/companySize) crashed with
                    "industry.join is not a function" — pinned by the walk. */}
                <Criterion label={lang === "ar" ? "القطاع" : "Industry"} value={asText(icp.criteria.industry)} />
                <Criterion label={lang === "ar" ? "الموقع" : "Location"} value={asText(icp.criteria.location) || cityList(icp.criteria.cities)} />
                <Criterion label={lang === "ar" ? "كلمات مفتاحية" : "Keywords"} value={[...(icp.criteria.keywords_ar || []), ...(icp.criteria.keywords_en || [])].join("، ")} />
                <Criterion label={lang === "ar" ? "الحد الأدنى للفروع" : "Min branches"} value={icp.criteria.criteria?.min_branches ? String(icp.criteria.criteria.min_branches) : null} />
                <Criterion label={lang === "ar" ? "ملاحظات" : "Notes"} value={asText(icp.criteria.criteria?.notes)} />
                <Criterion label={lang === "ar" ? "حدود البحث" : "Search budget"} value={icp.criteria.v0_limits?.max_search_queries ? `${icp.criteria.v0_limits.max_search_queries} ${lang === "ar" ? "استعلام" : "queries"}` : null} />
              </div>

              {icp.changes && (
                <div className="pt-3 border-t border-border text-xs text-muted-foreground">
                  <span className="font-medium text-foreground">{t("icp.changes")}: </span>{icp.changes}
                </div>
              )}

              {usedBy.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {usedBy.map((j) => <span key={j.id} className="text-[11px] tnum text-muted-foreground rounded-md border border-border px-2 py-0.5">{j.id} · {statusLabel(j.status, lang)}</span>)}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </>
  );
}

function Criterion({ label, value }) {
  return (
    <div className="flex items-center gap-2">
      <Check className="w-3.5 h-3.5 text-[hsl(var(--success))] shrink-0" />
      <span className="text-muted-foreground">{label}:</span>
      <span className="font-medium">{value || "—"}</span>
    </div>
  );
}

// shape-tolerant readers: the definition mixes strings, arrays and objects
const asText = (v) => (Array.isArray(v) ? v.join("، ") : v == null || v === "" ? null : String(v));
const cityList = (cities) => (Array.isArray(cities) ? cities.map((c) => c?.name).filter(Boolean).join("، ") : null);