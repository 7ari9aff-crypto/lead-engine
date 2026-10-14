import React from "react";
import { useLeadEngine } from "@/lib/leadEngine/store";
import { PageHeader } from "@/components/leadEngine/PageHeader";
import { Pill, ProgressBar, StaleBanner, ConnectionEmpty, TimeAgo } from "@/components/leadEngine/primitives";
import { listEmptyKind } from "@/lib/leadEngine/connState";
import { Server, HelpCircle } from "lucide-react";

const TASK_LABELS = {
  web_search: { ar: "بحث ويب", en: "Web search" },
  reasoning: { ar: "استدلال", en: "Reasoning" },
  inference: { ar: "استنتاج", en: "Inference" },
  people_search: { ar: "بحث أشخاص", en: "People search" },
  org_search: { ar: "بحث منشآت", en: "Org search" },
  enrichment: { ar: "إثراء بيانات", en: "Enrichment" },
  email_verify: { ar: "فحص إيميل", en: "Email verify" },
  email_find: { ar: "إيجاد إيميل", en: "Email find" },
  deep_research: { ar: "بحث عميق", en: "Deep research" },
};

const STATUS_LABELS = {
  OPERATIONAL: { ar: "يعمل", en: "Operational" },
  DEGRADED: { ar: "متوقف مؤقتًا", en: "Cooling down" },
  EXHAUSTED: { ar: "نفدت الحصة", en: "Quota exhausted" },
  DISCONNECTED: { ar: "غير مربوط", en: "Not connected" },
  UNKNOWN: { ar: "غير معروف", en: "Unknown" },
};

export default function Providers() {
  const { t, lang, providers, connected, lastSuccessAt, everLoaded, lastError, refresh } = useLeadEngine();
  const ar = lang === "ar";
  const emptyKind = listEmptyKind({ connected, everLoaded, lastError, total: providers.length, filtered: providers.length });

  return (
    <>
      <PageHeader title={t("providers.title")} subtitle={ar ? "حالة كل مزود بيانات، وحصته، ولماذا يستخدمه النظام." : "Each data provider's health, quota, and why the system uses it."} />
      <div className="px-4 lg:px-8 py-6 max-w-[1300px] space-y-3">
        {!connected && <StaleBanner lastSuccessAt={lastSuccessAt} onRetry={refresh} />}

        {providers.length === 0 && emptyKind === "loading" && (
          <p className="text-sm text-muted-foreground py-6 text-center">{ar ? "جارٍ تحميل المزوّدين…" : "Loading providers…"}</p>
        )}
        {providers.length === 0 && emptyKind === "backend-down" && <ConnectionEmpty onRetry={refresh} />}
        {providers.length === 0 && emptyKind === "genuinely-empty" && (
          <p className="text-sm text-muted-foreground py-6 text-center">{ar ? "لا مزودين مسجلين." : "No providers registered."}</p>
        )}

        {providers.map((p) => {
          const pct = p.quota.limit ? Math.round((p.quota.used / p.quota.limit) * 100) : null;
          const statusMeta = STATUS_LABELS[p.status] || { ar: p.status, en: p.status };
          const taskMeta = TASK_LABELS[p.task] || { ar: p.task, en: p.task };
          return (
            <div key={p.id} className="card-surface p-5">
              <div className="flex flex-col lg:flex-row lg:items-center gap-4 mb-3">
                <div className="flex items-center gap-3 flex-1 min-w-0">
                  <div className="w-10 h-10 rounded-lg bg-muted grid place-items-center"><Server className="w-5 h-5 text-muted-foreground" /></div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="font-semibold">{p.name}</h3>
                      <Pill tone={p.status === "OPERATIONAL" ? "success" : p.status === "DISCONNECTED" ? "danger" : p.status === "EXHAUSTED" ? "warning" : "warning"}>{statusMeta[lang] || statusMeta.ar}</Pill>
                      {!p.hasKey && <Pill tone="slate">{ar ? "بدون مفتاح" : "no key"}</Pill>}
                    </div>
                    <div className="text-xs text-muted-foreground mt-0.5">
                      {taskMeta[lang] || taskMeta.ar} · {ar ? "الأولوية" : "priority"} <span className="tnum">{p.priority ?? "—"}</span>
                      {p.period && p.period !== "none" && <> · {ar ? "دورة" : "period"} {p.period}</>}
                    </div>
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-4 text-xs lg:text-end">
                  <div><div className="text-muted-foreground">{ar ? "مستهلك" : "Used"}</div><div className="font-display font-semibold tnum">{p.quota.used.toLocaleString()}</div></div>
                  <div>
                    <div className="text-muted-foreground">{ar ? "الحصة" : "Quota"}</div>
                    <div className="font-display font-semibold tnum">{p.quota.limit != null ? p.quota.limit.toLocaleString() : (ar ? "غير محدودة" : "unlimited")}</div>
                  </div>
                  <div>
                    <div className="text-muted-foreground">{ar ? "المتبقي" : "Remaining"}</div>
                    <div className="font-display font-semibold tnum">{p.remaining != null ? p.remaining.toLocaleString() : "—"}</div>
                  </div>
                </div>
              </div>
              {pct != null && (
                <div className="mb-3">
                  <div className="flex justify-between text-[11px] text-muted-foreground mb-1"><span>{ar ? "الاستخدام" : "Usage"}</span><span className="tnum">{pct}%</span></div>
                  <ProgressBar value={pct} tone={pct > 80 ? "warning" : "info"} />
                </div>
              )}
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground mb-3">
                <span className="tnum">{ar ? "نداءات" : "calls"}: {p.calls.toLocaleString()}</span>
                <span className="tnum">{ar ? "وحدات" : "units"}: {p.units.toLocaleString()}</span>
                {p.lastUsed && <span>{ar ? "آخر استخدام" : "last used"}: <TimeAgo iso={p.lastUsed} /></span>}
                {p.rpmLimit != null && <span className="tnum">RPM ≤ {p.rpmLimit}</span>}
                {p.modelName && <span className="font-mono">{p.modelName}</span>}
              </div>
              {(p.health || p.lastFailure) && (
                <div className="rounded-lg bg-muted/40 p-3 flex gap-2">
                  <HelpCircle className="w-4 h-4 text-muted-foreground shrink-0 mt-0.5" />
                  <div>
                    <div className="text-[11px] font-medium mb-0.5">{ar ? "حالة المزود" : "Provider state"}</div>
                    <p className="text-xs text-muted-foreground leading-relaxed" dir="auto">{p.health || p.lastFailure}</p>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </>
  );
}
