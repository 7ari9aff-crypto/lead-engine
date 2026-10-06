import React from "react";
import { cn } from "@/lib/utils";
import { useLeadEngine } from "@/lib/leadEngine/store";
import { PageHeader } from "@/components/leadEngine/PageHeader";
import { StatusBadge } from "@/components/leadEngine/primitives";
import { Bot, Check, X, ShieldAlert, Activity as ActivityIcon, Cpu } from "lucide-react";

export default function Agents() {
  const { t, lang, agents } = useLeadEngine();
  return (
    <>
      <PageHeader title={t("agents.title")} subtitle={lang === "ar" ? "الوكلاء الذين ينفّذون البحث، وما يُسمح لهم به وما يُمنع عنهم." : "The agents that run research — what they may do and what is blocked."} />
      <div className="px-4 lg:px-8 py-6 max-w-[1300px] space-y-4">
        {/* policy callout — capability vs permission */}
        <div className="rounded-xl border border-[hsl(var(--primary)/0.25)] bg-accent p-4 flex gap-3">
          <div className="w-9 h-9 shrink-0 rounded-lg bg-[hsl(var(--primary)/0.12)] text-[hsl(var(--primary))] grid place-items-center">
            <ShieldAlert className="w-5 h-5" />
          </div>
          <div className="min-w-0">
            <div className="text-sm font-semibold text-foreground">{lang === "ar" ? "القدرة ≠ الإذن" : "Capability ≠ permission"}</div>
            <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">{t("agents.capabilityNote")}</p>
          </div>
        </div>

        {agents.map((a) => (
          <div key={a.id} className="card-surface p-5 lg:p-6">
            {/* header */}
            <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 pb-5 border-b border-border">
              <div className="flex items-center gap-3.5">
                <div className="w-11 h-11 rounded-xl bg-accent text-primary grid place-items-center">
                  <Bot className="w-5 h-5" />
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="font-display font-semibold text-[15px] tracking-tight">{a.name}</h3>
                    <span className="inline-flex items-center rounded-md border border-[hsl(var(--primary)/0.25)] bg-accent px-1.5 py-0.5 text-[10px] font-mono font-medium text-accent-foreground">{a.version}</span>
                  </div>
                  <div className="flex items-center gap-1.5 mt-1 text-[11px] text-muted-foreground">
                    <Cpu className="w-3 h-3" />
                    <span className="font-mono">{a.model}</span>
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-5 lg:gap-6 lg:ps-6 lg:border-s lg:border-border">
                <Stat label={lang === "ar" ? "تشغيلات" : "Runs"} value={a.recentRuns} />
                <Stat label={lang === "ar" ? "فشل" : "Failures"} value={a.failures} tone={a.failures ? "warning" : "neutral"} />
                <StatusBadge solid status={a.status === "ACTIVE" ? "VERIFIED" : "STALE"} />
              </div>
            </div>

            {/* tools — capability vs permission */}
            <div className="pt-5">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-3 flex items-center gap-1.5">
                <ActivityIcon className="w-3.5 h-3.5" />
                {lang === "ar" ? "الأدوات — القدرة مقابل الإذن" : "Tools — capability vs permission"}
              </div>
              <div className="flex flex-wrap gap-2">
                {a.tools.map((tool) => (
                  <span
                    key={tool.name}
                    className={cn(
                      "inline-flex items-center gap-2 rounded-lg border px-2.5 py-1.5 text-xs",
                      tool.permitted
                        ? "border-[hsl(var(--success)/0.25)] bg-[hsl(var(--success-soft))]"
                        : "border-[hsl(var(--danger)/0.25)] bg-[hsl(var(--danger-soft))]"
                    )}
                  >
                    {tool.permitted ? (
                      <Check className="w-3.5 h-3.5 text-[hsl(var(--success))]" />
                    ) : (
                      <X className="w-3.5 h-3.5 text-[hsl(var(--danger))]" />
                    )}
                    <span className={cn("font-mono font-medium", tool.permitted ? "text-[hsl(var(--success-ink))]" : "text-[hsl(var(--danger-ink))]")}>{tool.name}</span>
                    <span className="text-muted-foreground" dir="auto">· {tool.capability}</span>
                    {!tool.permitted && (
                      <span className="text-[10px] font-medium text-[hsl(var(--danger-ink))] border border-[hsl(var(--danger)/0.25)] rounded px-1 py-px">{lang === "ar" ? "ممنوع" : "blocked"}</span>
                    )}
                  </span>
                ))}
              </div>
            </div>

            {/* footer note */}
            {a.note && (
              <div className="mt-5 pt-4 border-t border-border flex gap-2.5">
                <span className="w-1 h-1 rounded-full bg-muted-foreground mt-1.5 shrink-0" />
                <p dir="auto" className="text-xs text-muted-foreground leading-relaxed">{a.note}</p>
              </div>
            )}
          </div>
        ))}
      </div>
    </>
  );
}

function Stat({ label, value, tone = "primary" }) {
  return (
    <div className="text-center">
      <div className={cn(
        "font-display font-semibold tnum text-lg leading-none",
        tone === "warning" && "text-[hsl(var(--warning-ink))]",
        tone === "neutral" && "text-muted-foreground"
      )}>
        {value}
      </div>
      <div className="text-[10px] text-muted-foreground mt-1 uppercase tracking-wider">{label}</div>
    </div>
  );
}