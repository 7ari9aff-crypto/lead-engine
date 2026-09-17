import { cn } from "@/lib/utils";
import { StatTile } from "@/components/ui/StatTile";

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
  icon,
  label,
  value,
  detail,
  tone = "accent",
  onClick,
  loading,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string | number | null | undefined;
  detail?: string;
  tone?: "accent" | "success" | "warn" | "danger" | "info";
  onClick?: () => void;
  loading?: boolean;
}) {
  // One shared metric primitive keeps every KPI row visually identical.
  return (
    <StatTile
      icon={icon}
      label={label}
      value={value}
      detail={detail}
      tone={tone}
      onClick={onClick}
      loading={loading}
    />
  );
}
