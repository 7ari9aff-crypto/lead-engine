import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function PageHeader({
  icon,
  title,
  description,
  action,
}: {
  icon: ReactNode;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between flex-wrap gap-3">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2.5">
          <span className="flex items-center justify-center h-8 w-8 rounded-lg gradient-bg shrink-0">
            {icon}
          </span>
          {title}
        </h1>
        {description && (
          <p className="text-sm text-[var(--fg-muted)] mt-1.5">{description}</p>
        )}
      </div>
      {action && <div className="flex items-center gap-2">{action}</div>}
    </div>
  );
}
