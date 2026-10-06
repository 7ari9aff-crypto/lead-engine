import React from "react";
import { cn } from "@/lib/utils";
import { useLeadEngine } from "@/lib/leadEngine/store";
import { PageHeader } from "@/components/leadEngine/PageHeader";
import { StatusBadge, Pill, TONE_BG } from "@/components/leadEngine/primitives";
import { BarChart3 } from "lucide-react";

export default function Analytics() {
  const { t, lang, jobs, leads, providers } = useLeadEngine();

  // aggregate funnel from job stages (real data, no hardcoding)
  const funnel = ["discovered", "deduplicated", "researched", "verified", "qualified", "readyForReview"].map((k) => ({
    key: k,
    label: { discovered: lang === "ar" ? "مكتشفة" : "Discovered", deduplicated: lang === "ar" ? "بعد التكرار" : "Deduped", researched: lang === "ar" ? "تم البحث" : "Researched", verified: lang === "ar" ? "تم التحقق" : "Verified", qualified: lang === "ar" ? "مؤهلة" : "Qualified", readyForReview: lang === "ar" ? "جاهزة للمراجعة" : "Ready for review" }[k],
    value: jobs.reduce((a, j) => a + ((j.stages?.[k] || 0)), 0),
  }));
  const maxFunnel = Math.max(...funnel.map((f) => f.value), 1);

  // review outcomes from leads
  const outcomes = [
    { key: "APPROVED", value: leads.filter((l) => l.status === "APPROVED").length, tone: "success" },
    { key: "REJECTED", value: leads.filter((l) => l.status === "REJECTED").length, tone: "danger" },
    { key: "READY_FOR_REVIEW", value: leads.filter((l) => l.status === "READY_FOR_REVIEW").length, tone: "primary" },
    { key: "SAVED", value: leads.filter((l) => l.status === "SAVED").length, tone: "slate" },
    { key: "IN_RESEARCH", value: leads.filter((l) => l.status === "IN_RESEARCH").length, tone: "info" },
  ];
  const totalLeads = leads.length || 1;

  // verification coverage buckets
  const coverage = [
    { label: "90%+", value: leads.filter((l) => l.evidenceCoverage >= 90).length },
    { label: "70–89%", value: leads.filter((l) => l.evidenceCoverage >= 70 && l.evidenceCoverage < 90).length },
    { label: "<70%", value: leads.filter((l) => l.evidenceCoverage < 70).length },
  ];

  // provider usage
  const providerUsage = providers.map((p) => ({ name: p.name, used: p.usage, quota: p.quota, pct: Math.round((p.usage / p.quota) * 100) }));

  return (
    <>
      <PageHeader title={t("analytics.title")} subtitle={lang === "ar" ? "من الاكتشاف حتى المراجعة، عبر كل وظائف البحث." : "From discovery to review, across all research jobs."} />
      <div className="px-4 lg:px-8 py-6 max-w-[1300px] space-y-6">
        {/* funnel */}
        <section className="card-surface p-5">
          <h3 className="text-sm font-semibold mb-4 flex items-center gap-2"><BarChart3 className="w-4 h-4 text-muted-foreground" /> {lang === "ar" ? "مسار البحث" : "Research funnel"}</h3>
          <div className="space-y-3">
            {funnel.map((f, i) => (
              <div key={f.key} className="flex items-center gap-3">
                <span className="w-28 text-xs text-muted-foreground shrink-0">{f.label}</span>
                <div className="flex-1 h-7 rounded-lg bg-muted overflow-hidden relative">
                  <div className="h-full rounded-lg transition-all duration-700" style={{ width: `${(f.value / maxFunnel) * 100}%`, background: "hsl(var(--foreground) / 0.16)" }} />
                  <span className="absolute inset-y-0 end-2 flex items-center text-xs font-display font-semibold tnum text-foreground">{f.value}</span>
                </div>
                {i > 0 && <span className="text-[10px] text-muted-foreground tnum w-12 text-end shrink-0">{Math.round((f.value / (funnel[i - 1].value || 1)) * 100)}%</span>}
              </div>
            ))}
          </div>
        </section>

        <div className="grid lg:grid-cols-2 gap-6">
          {/* outcomes */}
          <section className="card-surface p-5">
            <h3 className="text-sm font-semibold mb-4">{lang === "ar" ? "نتائج المراجعة" : "Review outcomes"}</h3>
            <div className="space-y-3">
              {outcomes.map((o) => (
                <div key={o.key} className="flex items-center gap-3">
                  <StatusBadge status={o.key} />
                  <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
                    <div className={cn("h-full rounded-full", TONE_BG[o.tone] || TONE_BG.slate)} style={{ width: `${(o.value / totalLeads) * 100}%` }} />
                  </div>
                  <span className="text-sm font-display font-semibold tnum w-10 text-end">{o.value}</span>
                </div>
              ))}
            </div>
            <div className="mt-3 pt-3 border-t border-border text-xs text-muted-foreground">{lang === "ar" ? "نسبة الاعتماد" : "Approval rate"}: <b className="text-foreground tnum">{Math.round((outcomes[0].value / (outcomes[0].value + outcomes[1].value || 1)) * 100)}%</b></div>
          </section>

          {/* coverage */}
          <section className="card-surface p-5">
            <h3 className="text-sm font-semibold mb-4">{lang === "ar" ? "توزيع تغطية الأدلة" : "Evidence coverage distribution"}</h3>
            <div className="grid grid-cols-3 gap-3">
              {coverage.map((c) => (
                <div key={c.label} className="rounded-lg border border-border p-4 text-center">
                  <div className="text-2xl font-display font-semibold tnum">{c.value}</div>
                  <div className="text-[11px] text-muted-foreground mt-1">{c.label}</div>
                </div>
              ))}
            </div>
          </section>
        </div>

        {/* provider usage */}
        <section className="card-surface p-5">
          <h3 className="text-sm font-semibold mb-4">{lang === "ar" ? "استخدام المزودين" : "Provider usage"}</h3>
          <div className="space-y-3">
            {providerUsage.map((p) => (
              <div key={p.name} className="flex items-center gap-3">
                <span className="w-28 text-sm shrink-0">{p.name}</span>
                <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
                  <div className="h-full rounded-full bg-[hsl(var(--info))]" style={{ width: `${p.pct}%` }} />
                </div>
                <span className="text-xs text-muted-foreground tnum w-24 text-end">{p.used.toLocaleString()} / {p.quota.toLocaleString()}</span>
                <Pill tone={p.pct > 80 ? "warning" : "success"}>{p.pct}%</Pill>
              </div>
            ))}
          </div>
        </section>
      </div>
    </>
  );
}