import React from "react";
import { cn } from "@/lib/utils";
import { useLeadEngine } from "@/lib/leadEngine/store";
import { PageHeader } from "@/components/leadEngine/PageHeader";
import { Pill, TimeAgo, StaleBanner, ConnectionEmpty } from "@/components/leadEngine/primitives";
import { listEmptyKind } from "@/lib/leadEngine/connState";
import { Bot, ShieldAlert, Wrench } from "lucide-react";

// agent.status in the DB is a plain 'active'/'draft' lifecycle state.
const AGENT_STATUS_META = {
  active: { ar: "نشط", en: "Active", tone: "success" },
  draft: { ar: "مسودة", en: "Draft", tone: "slate" },
  disabled: { ar: "معطّل", en: "Disabled", tone: "danger" },
};

export default function Agents() {
  const { t, lang, agents, tools, connected, lastSuccessAt, everLoaded, lastError, secondaryLoaded, refresh } = useLeadEngine();
  const ar = lang === "ar";
  const emptyKind = listEmptyKind({ connected, everLoaded, lastError, total: agents.length, filtered: agents.length });

  return (
    <>
      <PageHeader title={t("agents.title")} subtitle={ar ? "الوكلاء الذين ينفّذون البحث، وما يُسمح لهم به وما يُمنع عنهم." : "The agents that run research — what they may do and what is blocked."} />
      <div className="px-4 lg:px-8 py-6 max-w-[1300px] space-y-4">
        {!connected && <StaleBanner lastSuccessAt={lastSuccessAt} onRetry={refresh} />}

        {/* policy callout — capability vs permission */}
        <div className="rounded-xl border border-[hsl(var(--primary)/0.25)] bg-accent p-4 flex gap-3">
          <div className="w-9 h-9 shrink-0 rounded-lg bg-[hsl(var(--primary)/0.12)] text-[hsl(var(--primary))] grid place-items-center">
            <ShieldAlert className="w-5 h-5" />
          </div>
          <div className="min-w-0">
            <div className="text-sm font-semibold text-foreground">{ar ? "القدرة ≠ الإذن" : "Capability ≠ permission"}</div>
            <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">{t("agents.capabilityNote")}</p>
          </div>
        </div>

        {/* FAIL-02: before the agents feed answers, never claim "none exist" */}
        {!secondaryLoaded && agents.length === 0 && (
          <p className="text-sm text-muted-foreground py-6 text-center">{ar ? "جارٍ تحميل الوكلاء…" : "Loading agents…"}</p>
        )}
        {agents.length === 0 && emptyKind === "backend-down" && <ConnectionEmpty onRetry={refresh} />}
        {agents.length === 0 && emptyKind === "genuinely-empty" && secondaryLoaded && (
          <p className="text-sm text-muted-foreground py-6 text-center">{ar ? "لا وكلاء مسجلون بعد." : "No agents registered yet."}</p>
        )}

        {agents.map((a) => {
          const statusMeta = AGENT_STATUS_META[a.status] || AGENT_STATUS_META.draft;
          return (
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
                      {a.version && (
                        <span className="inline-flex items-center rounded-md border border-[hsl(var(--primary)/0.25)] bg-accent px-1.5 py-0.5 text-[10px] font-mono font-medium text-accent-foreground">v{a.version}</span>
                      )}
                    </div>
                    <div className="flex items-center gap-1.5 mt-1 text-[11px] text-muted-foreground">
                      <span className="font-mono">{a.slug}</span>
                      {a.lastRunAt && <>· <TimeAgo iso={a.lastRunAt} /></>}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-5 lg:gap-6 lg:ps-6 lg:border-s lg:border-border">
                  <Stat label={ar ? "تشغيلات" : "Runs"} value={a.recentRuns} />
                  <Stat label={ar ? "فشل" : "Failures"} value={a.failures} tone={a.failures ? "warning" : "neutral"} />
                  <Pill tone={statusMeta.tone}>{statusMeta[lang] || statusMeta.ar}</Pill>
                </div>
              </div>

              {/* footer note */}
              {a.note && (
                <div className="pt-4 flex gap-2.5">
                  <span className="w-1 h-1 rounded-full bg-muted-foreground mt-1.5 shrink-0" />
                  <p dir="auto" className="text-xs text-muted-foreground leading-relaxed">{a.note}</p>
                </div>
              )}
            </div>
          );
        })}

        {/* the tool registry — what exists and what is gated, from /api/tools */}
        <div className="card-surface p-5">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-3 flex items-center gap-1.5">
            <Wrench className="w-3.5 h-3.5" />
            {ar ? `سجل الأدوات (${tools.length})` : `Tool registry (${tools.length})`}
          </div>
          {tools.length === 0 ? (
            <p className="text-sm text-muted-foreground py-2">{secondaryLoaded ? (connected ? (ar ? "لا أدوات مسجلة." : "No tools registered.") : (ar ? "تعذّر تحميل سجل الأدوات." : "Could not load the tool registry.")) : (ar ? "جارٍ تحميل الأدوات…" : "Loading tools…")}</p>
          ) : (
            <div className="divide-y divide-border">
              {tools.map((tool) => (
                <div key={tool.name} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2.5">
                  <span className="font-mono text-xs font-medium">{tool.name}</span>
                  {!tool.enabled && <Pill tone="danger">{ar ? "معطّلة" : "disabled"}</Pill>}
                  {tool.requiresApproval && <Pill tone="warning">{ar ? "تحتاج موافقة" : "approval"}</Pill>}
                  {tool.scopes.map((s) => <Pill key={s}>{s}</Pill>)}
                  <span className="text-xs text-muted-foreground basis-full lg:basis-auto lg:ms-auto lg:max-w-[50%] truncate" dir="auto" title={tool.description}>{tool.description}</span>
                </div>
              ))}
            </div>
          )}
        </div>
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
