import { cn, formatNumber } from "@/lib/utils";

/**
 * StatTile — the dashboard's metric primitive.
 *
 * One component for every number the operator cares about: label, big value,
 * optional delta (honest direction+color), optional sparkline, and a tone.
 * Consistent geometry is what makes a dashboard look designed instead of
 * assembled; every page builds its KPI rows from this.
 */
export type StatTone = "accent" | "success" | "warn" | "danger" | "info";

const TONE_VAR: Record<StatTone, string> = {
  accent: "var(--accent)",
  success: "var(--success)",
  warn: "var(--warn)",
  danger: "var(--danger)",
  info: "var(--info)",
};

export function StatTile({
  icon: Icon,
  label,
  value,
  detail,
  delta,
  spark,
  tone = "accent",
  onClick,
  loading,
  className,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string | number | null | undefined;
  detail?: string;
  /** Signed change vs the previous period; drives the arrow + color. */
  delta?: { value: number; label?: string } | null;
  spark?: number[];
  tone?: StatTone;
  onClick?: () => void;
  loading?: boolean;
  className?: string;
}) {
  const color = TONE_VAR[tone];
  const up = (delta?.value ?? 0) > 0;
  const flat = (delta?.value ?? 0) === 0;

  return (
    <div
      onClick={onClick}
      className={cn(
        "group relative overflow-hidden rounded-2xl border border-[var(--border)]",
        "bg-[var(--bg-elev)] shadow-[var(--shadow)] p-4",
        "transition-all duration-200 hover:shadow-[var(--shadow-lg)]",
        onClick && "cursor-pointer hover:-translate-y-0.5 hover:border-[var(--accent)]/40",
        className
      )}
    >
      {/* tone wash */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 -top-16 h-24 opacity-70"
        style={{ background: `radial-gradient(60% 100% at 50% 100%, color-mix(in srgb, ${color} 10%, transparent), transparent)` }}
      />
      <div className="relative flex items-start justify-between gap-2">
        <span className="text-[12px] font-medium text-[var(--fg-muted)] leading-5">{label}</span>
        <span
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl transition-transform duration-200 group-hover:scale-105"
          style={{
            background: `color-mix(in srgb, ${color} 12%, transparent)`,
            color,
          }}
        >
          <Icon className="h-4 w-4" />
        </span>
      </div>

      <div className="relative mt-1 flex items-end gap-2">
        {loading ? (
          <span className="inline-block h-7 w-16 animate-pulse rounded-md bg-[var(--bg-soft)]" />
        ) : (
          <span className="text-[26px] font-black leading-none tracking-tight tabular-nums">
            {typeof value === "number" ? formatNumber(value) : (value ?? "—")}
          </span>
        )}
        {delta && !loading && (
          <span
            className={cn(
              "mb-0.5 inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10.5px] font-bold",
              flat
                ? "bg-[var(--bg-soft)] text-[var(--fg-soft)]"
                : up
                ? "bg-[color-mix(in_srgb,var(--success)_14%,transparent)] text-[var(--success)]"
                : "bg-[color-mix(in_srgb,var(--danger)_14%,transparent)] text-[var(--danger)]"
            )}
          >
            {flat ? "—" : up ? "▲" : "▼"}
            {Math.abs(delta.value)}
            {delta.label && <span className="font-medium opacity-70">{delta.label}</span>}
          </span>
        )}
      </div>

      {detail && (
        <div className="relative mt-1.5 truncate text-[11.5px] text-[var(--fg-soft)]">{detail}</div>
      )}

      {spark && spark.length > 1 && (
        <div className="relative mt-2 flex h-8 items-end gap-[3px]" aria-hidden>
          {spark.slice(-24).map((v, i, arr) => {
            const max = Math.max(...arr, 1);
            return (
              <span
                key={i}
                className="flex-1 rounded-sm transition-all"
                style={{
                  height: `${Math.max(8, (v / max) * 100)}%`,
                  background: `color-mix(in srgb, ${color} ${i === arr.length - 1 ? 70 : 35}%, transparent)`,
                }}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}
