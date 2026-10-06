import React from "react";
import { cn } from "@/lib/utils";
import { useLeadEngine } from "@/lib/leadEngine/store";
import { PageHeader } from "@/components/leadEngine/PageHeader";
import { Pill, ConfirmButton } from "@/components/leadEngine/primitives";
import { Blocks, Check, Plus, Clock, X } from "lucide-react";

const STATE_META = {
  connected: { ar: "مربوط", en: "Connected", tone: "success", icon: Check },
  available: { ar: "متاح للربط", en: "Available", tone: "slate", icon: Plus },
  coming_later: { ar: "قريبًا", en: "Coming later", tone: "slate", icon: Clock },
};

export default function Integrations() {
  const { t, lang, integrations, toggleIntegration } = useLeadEngine();
  const ar = lang === "ar";
  return (
    <>
      <PageHeader title={t("integrations.title")} subtitle={ar ? "اربط الأدوات التي يستخدمها فريقك. النظام لا يرسل أي رسائل بنفسه." : "Connect the tools your team uses. The system never sends messages on its own."} />
      <div className="px-4 lg:px-8 py-6 max-w-[1300px]">
        {integrations.length === 0 ? (
          <div className="card-surface p-10 text-center text-sm text-muted-foreground">{t("empty.integrations")}</div>
        ) : (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {integrations.map((it) => {
              const meta = STATE_META[it.state];
              return (
                <div key={it.id} className={cn("card-surface p-5 flex flex-col", it.state === "coming_later" && "opacity-75")}>
                  <div className="flex items-start justify-between mb-3">
                    <div className="w-10 h-10 rounded-lg bg-muted grid place-items-center"><Blocks className="w-5 h-5 text-muted-foreground" /></div>
                    <Pill tone={meta.tone}><meta.icon className="w-3 h-3" /> {meta[lang]}</Pill>
                  </div>
                  <h3 className="font-semibold">{it.name}</h3>
                  <div className="text-[11px] text-muted-foreground mt-0.5">{it.category}</div>
                  <p className="text-xs text-muted-foreground mt-2 leading-relaxed flex-1">{it.note}</p>
                  {it.state === "connected" ? (
                    <ConfirmButton onConfirm={() => toggleIntegration(it.id)} confirmLabel={ar ? "تأكيد الفصل؟" : "Confirm disconnect?"}
                      className="mt-3 rounded-lg border border-border py-2 text-xs font-medium hover:bg-muted transition inline-flex items-center justify-center gap-1.5 w-full"
                      confirmClassName="mt-3 rounded-lg bg-[hsl(var(--danger))] text-white py-2 text-xs font-medium w-full">
                      <X className="w-3.5 h-3.5" /> {ar ? "فصل" : "Disconnect"}
                    </ConfirmButton>
                  ) : it.state === "available" ? (
                    <button onClick={() => toggleIntegration(it.id)} className="mt-3 rounded-lg bg-primary text-primary-foreground py-2 text-xs font-medium hover:opacity-90 transition inline-flex items-center justify-center gap-1.5"><Plus className="w-3.5 h-3.5" /> {ar ? "ربط" : "Connect"}</button>
                  ) : (
                    <div className="mt-3 rounded-lg border border-dashed border-border py-2 text-xs text-muted-foreground text-center">{t("common.unsupported")}</div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}
