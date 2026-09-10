import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center py-12 px-6 text-center",
        "border-2 border-dashed border-[var(--border)] rounded-xl bg-[var(--bg-soft)]/50",
        className
      )}
    >
      {icon && <div className="mb-3 text-[var(--fg-soft)] opacity-70">{icon}</div>}
      <h3 className="text-base font-semibold text-[var(--fg)] mb-1">{title}</h3>
      {description && (
        <p className="text-sm text-[var(--fg-muted)] max-w-sm mb-4">{description}</p>
      )}
      {action}
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-block h-4 w-4 rounded-full border-2 border-current border-t-transparent animate-spin",
        className
      )}
    />
  );
}
