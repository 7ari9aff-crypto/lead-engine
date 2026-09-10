import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors [&_svg]:size-3",
  {
    variants: {
      variant: {
        default: "bg-[var(--bg-soft)] text-[var(--fg-muted)] border border-[var(--border)]",
        accent: "bg-[var(--accent-soft)] text-[var(--accent)] border border-transparent",
        success: "bg-[color-mix(in_srgb,var(--success)_15%,transparent)] text-[var(--success)]",
        warn: "bg-[color-mix(in_srgb,var(--warn)_15%,transparent)] text-[var(--warn)]",
        danger: "bg-[color-mix(in_srgb,var(--danger)_15%,transparent)] text-[var(--danger)]",
        info: "bg-[color-mix(in_srgb,var(--info)_15%,transparent)] text-[var(--info)]",
        outline: "border border-[var(--border)] text-[var(--fg-muted)]",
      },
    },
    defaultVariants: { variant: "default" },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export function StatusDot({ status }: { status: string }) {
  const map: Record<string, string> = {
    ACTIVE: "var(--success)",
    COMPLETED: "var(--success)",
    DELIVERABLE: "var(--success)",
    ACCEPTED: "var(--success)",
    RUNNING: "var(--info)",
    RESUMING: "var(--info)",
    DEGRADED: "var(--warn)",
    RISKY: "var(--warn)",
    REVIEW: "var(--warn)",
    CATCH_ALL: "var(--warn)",
    PAUSED: "var(--warn)",
    QUEUED: "var(--info)",
    PENDING: "var(--info)",
    EXHAUSTED: "var(--danger)",
    DISABLED: "var(--fg-soft)",
    FAILED: "var(--danger)",
    INVALID: "var(--danger)",
    REJECTED: "var(--danger)",
    UNKNOWN: "var(--fg-soft)",
  };
  const color = map[status] || "var(--fg-soft)";
  return (
    <span
      className="inline-block h-2 w-2 rounded-full pulse-dot"
      style={{ color, background: color }}
    />
  );
}
