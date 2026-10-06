import React, { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import { useLeadEngine } from "@/lib/leadEngine/store";

// status → { ar, en, tone }
export const STATUS_META = {
  DISCOVERING: { ar: "يكتشف", en: "Discovering", tone: "info" },
  RESEARCHING: { ar: "يبحث", en: "Researching", tone: "info" },
  VERIFYING: { ar: "يتحقق", en: "Verifying", tone: "info" },
  QUALIFYING: { ar: "يؤهّل", en: "Qualifying", tone: "violet" },
  READY_FOR_REVIEW: { ar: "جاهزة للمراجعة", en: "Ready for review", tone: "primary" },
  COMPLETED: { ar: "مكتملة", en: "Completed", tone: "success" },
  PAUSED: { ar: "متوقفة مؤقتًا", en: "Paused", tone: "warning" },
  WAITING_FOR_USER: { ar: "تنتظر إجابتك", en: "Waiting for you", tone: "warning" },
  CANCELLED: { ar: "ملغاة", en: "Cancelled", tone: "slate" },
  FAILED: { ar: "فاشلة", en: "Failed", tone: "danger" },
  QUEUED: { ar: "في الانتظار", en: "Queued", tone: "slate" },
  RUNNING: { ar: "قيد التشغيل", en: "Running", tone: "info" },
  VERIFIED: { ar: "متحقق", en: "Verified", tone: "success" },
  CONFLICTED: { ar: "متعارض", en: "Conflicted", tone: "warning" },
  STALE: { ar: "قديم", en: "Stale", tone: "slate" },
  UNVERIFIED: { ar: "غير متحقق", en: "Unverified", tone: "slate" },
  INFERRED: { ar: "استنتاجي", en: "Inferred", tone: "violet" },
  APPROVED: { ar: "موافق عليها", en: "Approved", tone: "success" },
  REJECTED: { ar: "مرفوضة", en: "Rejected", tone: "danger" },
  SAVED: { ar: "محفوظة", en: "Saved", tone: "slate" },
  IN_RESEARCH: { ar: "قيد البحث", en: "In research", tone: "info" },
  PARTIALLY_VERIFIED: { ar: "تحقق جزئي", en: "Partially verified", tone: "warning" },
};

const TONE_CLASSES = {
  success: "bg-[hsl(var(--success-soft))] text-[hsl(var(--success-ink))] border-[hsl(var(--success)/0.3)]",
  warning: "bg-[hsl(var(--warning-soft))] text-[hsl(var(--warning-ink))] border-[hsl(var(--warning)/0.3)]",
  danger: "bg-[hsl(var(--danger-soft))] text-[hsl(var(--danger-ink))] border-[hsl(var(--danger)/0.3)]",
  info: "bg-[hsl(var(--info-soft))] text-[hsl(var(--info-ink))] border-border",
  violet: "bg-transparent text-[hsl(var(--violet-ink))] border-dashed border-[hsl(var(--violet))]",
  primary: "bg-transparent text-foreground border-[hsl(var(--foreground)/0.45)] font-semibold",
  slate: "bg-muted text-muted-foreground border-border",
};

// literal color maps (Tailwind must see full class strings)
export const TONE_BG = {
  success: "bg-[hsl(var(--success))]",
  warning: "bg-[hsl(var(--warning))]",
  danger: "bg-[hsl(var(--danger))]",
  info: "bg-[hsl(var(--info))]",
  violet: "bg-[hsl(var(--violet))]",
  primary: "bg-[hsl(var(--primary))]",
  slate: "bg-muted-foreground",
};
export const TONE_TEXT = {
  success: "text-[hsl(var(--success-ink))]",
  warning: "text-[hsl(var(--warning-ink))]",
  danger: "text-[hsl(var(--danger-ink))]",
  info: "text-[hsl(var(--info-ink))]",
  violet: "text-[hsl(var(--violet-ink))]",
  primary: "text-[hsl(var(--primary))]",
  slate: "text-muted-foreground",
};
export const TONE_BORDER_S = {
  success: "border-s-[hsl(var(--success))]",
  warning: "border-s-[hsl(var(--warning))]",
  danger: "border-s-[hsl(var(--danger))]",
  info: "border-s-[hsl(var(--info))]",
  violet: "border-s-[hsl(var(--violet))]",
  primary: "border-s-[hsl(var(--primary))]",
  slate: "border-s-border",
};

export const statusLabel = (status, lang) => (STATUS_META[status]?.[lang]) || status;

export function StatusBadge({ status, size = "sm", pulse = false, solid = false }) {
  const { lang } = useLeadEngine();
  const meta = STATUS_META[status] || { ar: status, en: status, tone: "slate" };
  const live = pulse || status === "RUNNING" || status === "DISCOVERING" || status === "RESEARCHING" || status === "VERIFYING" || status === "QUALIFYING";
  return (
    <span className={cn(
      "inline-flex items-center gap-1.5 rounded-full border font-medium tnum",
      size === "sm" ? "px-2.5 py-0.5 text-[11px]" : "px-3 py-1 text-xs",
      solid && meta.tone === "success" ? "bg-[hsl(var(--verified))] text-white border-transparent" : TONE_CLASSES[meta.tone]
    )}>
      {live && <span className={cn("w-1.5 h-1.5 rounded-full bg-current", pulse && "animate-pulse")} />}
      {meta[lang]}
    </span>
  );
}

export function Pill({ children, tone = "slate", className }) {
  return <span className={cn("inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-medium", TONE_CLASSES[tone], className)}>{children}</span>;
}

export function StatCard({ label, value, sub, icon: Icon, tone = "primary", to }) {
  return (
    <div className="card-surface card-hover p-4 flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground font-medium">{label}</span>
        {Icon && <span className={cn("w-7 h-7 rounded-lg grid place-items-center", TONE_CLASSES[tone])}><Icon className="w-4 h-4" /></span>}
      </div>
      <div className="text-2xl font-display font-semibold tracking-tight tnum">{value}</div>
      {sub && <div className="text-[11px] text-muted-foreground">{sub}</div>}
    </div>
  );
}

export function EmptyState({ icon: Icon, title, action, onAction, hint }) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-16 px-6 animate-fade-in">
      {Icon && (
        <div className="w-14 h-14 rounded-2xl bg-muted grid place-items-center mb-4 text-muted-foreground">
          <Icon className="w-7 h-7" />
        </div>
      )}
      <p className="text-base font-medium text-foreground mb-1">{title}</p>
      {hint && <p className="text-sm text-muted-foreground max-w-md mb-5">{hint}</p>}
      {action && onAction && (
        <button onClick={onAction} className="focus-ring rounded-lg bg-primary text-primary-foreground px-4 py-2 text-sm font-medium hover:opacity-90 transition">
          {action}
        </button>
      )}
    </div>
  );
}

export function ProgressBar({ value, max = 100, tone = "primary", className }) {
  const pct = Math.min(100, Math.round((value / max) * 100));
  const bar = {
    primary: "bg-primary dark:bg-primary/75", success: "bg-[hsl(var(--success))]", warning: "bg-[hsl(var(--warning))]",
    danger: "bg-[hsl(var(--danger))]", info: "bg-[hsl(var(--info))]", violet: "bg-[hsl(var(--violet))]",
  };
  return (
    <div className={cn("h-1.5 w-full rounded-full bg-muted overflow-hidden", className)}>
      <div className={cn("h-full rounded-full transition-all duration-700 ease-out", bar[tone])} style={{ width: `${pct}%` }} />
    </div>
  );
}

export function ScoreRing({ score, size = 56 }) {
  const r = (size - 6) / 2;
  const c = 2 * Math.PI * r;
  const off = c - (score / 100) * c;
  const tone = score >= 80 ? "hsl(var(--success))" : score >= 65 ? "hsl(var(--warning))" : "hsl(var(--danger))";
  return (
    <div className="relative grid place-items-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="hsl(var(--muted))" strokeWidth="4" />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={tone} strokeWidth="4" strokeLinecap="round" strokeDasharray={c} strokeDashoffset={off} style={{ transition: "stroke-dashoffset 0.6s ease" }} />
      </svg>
      <span className="absolute text-sm font-display font-semibold tnum">{score}</span>
    </div>
  );
}

export function SectionCard({ title, action, children, className, padded = true }) {
  return (
    <div className={cn("card-surface", padded && "p-4", className)}>
      {title && (
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-foreground">{title}</h3>
          {action}
        </div>
      )}
      {children}
    </div>
  );
}

// one shared clock so every "x min ago" stays correct without a timer per instance
const listeners = new Set();
let clock = null;
function useMinuteTick() {
  const [, set] = useState(0);
  useEffect(() => {
    const fn = () => set((n) => n + 1);
    listeners.add(fn);
    if (!clock) clock = setInterval(() => listeners.forEach((f) => f()), 30000);
    return () => { listeners.delete(fn); if (!listeners.size) { clearInterval(clock); clock = null; } };
  }, []);
}

export function TimeAgo({ iso }) {
  const { lang } = useLeadEngine();
  useMinuteTick();
  if (!iso) return <span className="text-muted-foreground">—</span>;
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  let str;
  if (mins < 1) str = lang === "ar" ? "الآن" : "now";
  else if (mins < 60) str = lang === "ar" ? `قبل ${mins} د` : `${mins}m ago`;
  else if (mins < 1440) str = lang === "ar" ? `قبل ${Math.floor(mins / 60)} س` : `${Math.floor(mins / 60)}h ago`;
  else str = lang === "ar" ? `قبل ${Math.floor(mins / 1440)} يوم` : `${Math.floor(mins / 1440)}d ago`;
  return <span className="tnum text-muted-foreground">{str}</span>;
}

export function MatchGlyph({ match }) {
  const { lang } = useLeadEngine();
  const label = { yes: ["مطابق", "Match"], no: ["غير مطابق", "No match"], partial: ["جزئي / غير مؤكد", "Partial / unconfirmed"] }[match] || ["", ""];
  const txt = label[lang === "ar" ? 0 : 1];
  if (match === "yes") return <span role="img" aria-label={txt} title={txt} className="text-[hsl(var(--success-ink))]">✓</span>;
  if (match === "no") return <span role="img" aria-label={txt} title={txt} className="text-[hsl(var(--danger-ink))]">✗</span>;
  return <span role="img" aria-label={txt} title={txt} className="text-[hsl(var(--warning-ink))]">?</span>;
}

// two-step button for destructive actions (no browser confirm dialogs)
export function ConfirmButton({ children, confirmLabel, onConfirm, className, confirmClassName }) {
  const [armed, setArmed] = useState(false);
  useEffect(() => { if (!armed) return; const id = setTimeout(() => setArmed(false), 4000); return () => clearTimeout(id); }, [armed]);
  return armed ? (
    <button onClick={() => { setArmed(false); onConfirm(); }} className={confirmClassName || className}>{confirmLabel}</button>
  ) : (
    <button onClick={() => setArmed(true)} className={className}>{children}</button>
  );
}