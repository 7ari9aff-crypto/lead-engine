import React from "react";
import { useLeadEngine } from "@/lib/leadEngine/store";
import { PageHeader } from "@/components/leadEngine/PageHeader";
import { Pill, ProgressBar } from "@/components/leadEngine/primitives";
import { Server, HelpCircle } from "lucide-react";

export default function Providers() {
  const { t, lang, providers } = useLeadEngine();
  return (
    <>
      <PageHeader title={t("providers.title")} subtitle={lang === "ar" ? "حالة كل مزود بيانات، وحصته، ولماذا يستخدمه النظام." : "Each data provider's health, quota, and why the system uses it."} />
      <div className="px-4 lg:px-8 py-6 max-w-[1300px] space-y-3">
        {providers.map((p) => {
          const pct = Math.round((p.usage / p.quota) * 100);
          return (
            <div key={p.id} className="card-surface p-5">
              <div className="flex flex-col lg:flex-row lg:items-center gap-4 mb-3">
                <div className="flex items-center gap-3 flex-1 min-w-0">
                  <div className="w-10 h-10 rounded-lg bg-muted grid place-items-center"><Server className="w-5 h-5 text-muted-foreground" /></div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <h3 className="font-semibold">{p.name}</h3>
                      <Pill tone={p.status === "OPERATIONAL" ? "success" : p.status === "DISCONNECTED" ? "danger" : "warning"}>{p.health}</Pill>
                    </div>
                    <div className="text-xs text-muted-foreground mt-0.5">{p.capability} · {p.fallbackPosition}</div>
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-4 text-xs lg:text-end">
                  <div><div className="text-muted-foreground">{lang === "ar" ? "الحصة" : "Quota"}</div><div className="font-display font-semibold tnum">{p.quota.toLocaleString()}</div></div>
                  <div><div className="text-muted-foreground">{lang === "ar" ? "المتبقي" : "Remaining"}</div><div className="font-display font-semibold tnum">{p.remaining.toLocaleString()}</div></div>
                  <div><div className="text-muted-foreground">{lang === "ar" ? "آخر فشل" : "Last failure"}</div><div className="text-xs">{p.lastFailure}</div></div>
                </div>
              </div>
              <div className="mb-3">
                <div className="flex justify-between text-[11px] text-muted-foreground mb-1"><span>{lang === "ar" ? "الاستخدام" : "Usage"}</span><span className="tnum">{pct}%</span></div>
                <ProgressBar value={pct} tone={pct > 80 ? "warning" : "info"} />
              </div>
              <div className="rounded-lg bg-muted/40 p-3 flex gap-2">
                <HelpCircle className="w-4 h-4 text-muted-foreground shrink-0 mt-0.5" />
                <div>
                  <div className="text-[11px] font-medium mb-0.5">{t("providers.why")}</div>
                  <p className="text-xs text-muted-foreground leading-relaxed">{p.rationale}</p>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}