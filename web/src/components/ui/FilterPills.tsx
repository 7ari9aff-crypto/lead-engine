import { cn } from "@/lib/utils";

export function FilterPills({
  options,
  value,
  onChange,
  className,
}: {
  options: { value: string; label: string }[];
  value: string;
  onChange: (v: string) => void;
  className?: string;
}) {
  return (
    <div className={cn("flex gap-1.5 flex-wrap", className)}>
      {options.map((opt) => {
        const active = value === opt.value;
        return (
          <button
            key={opt.value}
            onClick={() => onChange(opt.value)}
            className={cn(
              "px-3 py-1.5 rounded-full text-xs font-medium transition-all duration-200 select-none",
              active
                ? "bg-[var(--accent)] text-white shadow-sm shadow-[var(--accent-glow)]"
                : "bg-[var(--bg-soft)] text-[var(--fg-muted)] border border-[var(--border)] hover:border-[var(--accent)] hover:text-[var(--fg)]"
            )}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

export function StatCard({
  icon: Icon,
  label,
  value,
  detail,
  tone = "accent",
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string | number;
  detail?: string;
  tone?: "accent" | "success" | "warn" | "danger" | "info";
}) {
  const toneMap = {
    accent: "var(--accent)",
    success: "var(--success)",
    warn: "var(--warn)",
    danger: "var(--danger)",
    info: "var(--info)",
  } as const;

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-elev)] shadow-[var(--shadow)] card-hover p-4">
      <div className="flex items-center justify-between gap-2 mb-3">
        <span className="text-xs text-[var(--fg-muted)]">{label}</span>
        <div
          className="p-1.5 rounded-lg"
          style={{
            background: `color-mix(in srgb, ${toneMap[tone]} 12%, transparent)`,
            color: toneMap[tone],
          }}
        >
          <Icon className="h-3.5 w-3.5" />
        </div>
      </div>
      <div className="text-xl font-bold tabular-nums">{value}</div>
      {detail && <div className="text-[11px] text-[var(--fg-soft)] mt-1">{detail}</div>}
    </div>
  );
}
