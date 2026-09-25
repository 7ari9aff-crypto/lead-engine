import { RefreshCw, XCircle } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { friendlyError } from "@/lib/friendly";
import { cn } from "@/lib/utils";

/**
 * A real backend failure, shown as one.
 *
 * Distinct from `EmptyState`: an empty store and a broken store are different
 * truths, and the operator must never have to guess which one they are looking
 * at (gap register FAIL-01 / FAIL-03). Any list surface that has an `error` in
 * scope should branch on it *before* falling through to `EmptyState`.
 *
 * Deliberately not an `EmptyState` with a red icon: `EmptyState` draws a dashed
 * border, so an error rendered that way is one glance away from looking like
 * "nothing here yet". `--danger` matches the app's existing failure surfaces
 * (App.tsx error boundary, Overview, Pricing).
 *
 * Copy rules: Arabic only, no HTTP status, no English, no identifiers — the
 * technical detail stays in the console. `friendlyError()` is the single
 * translation layer, so this component never re-implements message logic.
 */
export function ErrorState({
  error,
  onRetry,
  subject = "البيانات",
  className,
}: {
  error: unknown;
  onRetry?: () => void;
  /** What failed to load, as a noun phrase: "سجل النشاط", "العملاء المحتملون". */
  subject?: string;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={cn(
        "p-10 text-center rounded-xl border border-[var(--danger)]/40",
        "bg-[color-mix(in_srgb,var(--danger)_8%,transparent)]",
        className
      )}
    >
      <div className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-xl bg-[color-mix(in_srgb,var(--danger)_16%,transparent)]">
        <XCircle className="h-5 w-5 text-[var(--danger)]" aria-hidden="true" />
      </div>
      <p className="text-sm font-semibold mb-1">تعذر تحميل {subject}</p>
      <p className="text-[13px] text-[var(--fg-muted)] leading-6 mb-4">{friendlyError(error)}</p>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          إعادة المحاولة
        </Button>
      )}
    </div>
  );
}
