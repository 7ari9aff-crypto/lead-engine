import { AlertTriangle, RefreshCw } from "lucide-react";
import { friendlyError } from "@/lib/friendly";

/**
 * Something is on screen, but one of its sources is broken — say so.
 *
 * `ErrorState` answers "nothing rendered because nothing loaded". This answers
 * the other truth: real (possibly stale) data IS visible while at least one
 * fetch failed, so hiding it would destroy work the operator can still use and
 * showing `ErrorState` alone would misreport what is on screen. Converting a
 * page to a blocking error is only correct when it has nothing local to show.
 *
 * Same copy rules as `ErrorState`: Arabic only, no HTTP status, no identifiers,
 * and all wording comes from `friendlyError()` — never re-derived here.
 */
export function StaleBanner({
  error,
  subject,
  onRetry,
}: {
  error: unknown;
  /** What is affected, as a noun phrase: "بعض بيانات الملخص". */
  subject: string;
  onRetry?: () => void;
}) {
  return (
    <div
      role="status"
      className="flex items-start gap-2.5 rounded-xl border border-[var(--warn)]/30 bg-[var(--warn)]/5 px-4 py-3 text-[12px] text-[var(--fg-muted)]"
    >
      <AlertTriangle className="h-4 w-4 text-[var(--warn)] mt-0.5 shrink-0" aria-hidden="true" />
      <span>
        {subject} لم تُحدّث: {friendlyError(error)}
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="ms-2 inline-flex items-center gap-1 font-semibold text-[var(--accent)] hover:underline"
          >
            <RefreshCw className="h-3 w-3" aria-hidden="true" />
            إعادة المحاولة
          </button>
        )}
      </span>
    </div>
  );
}

/**
 * "These numbers are not live" — the honest replacement for a count that would
 * otherwise read as a misleading `0` while its source is down.
 */
export const NOT_AVAILABLE = "غير متاح";
