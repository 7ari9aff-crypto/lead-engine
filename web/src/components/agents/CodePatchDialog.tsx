import { useEffect, useState } from "react";
import { AlertTriangle, Check, FileCode2, GitBranch, RotateCcw, ShieldCheck } from "lucide-react";
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Spinner } from "@/components/ui/EmptyState";
import { apiCode, apiGet, apiPost, type ApprovalDetail, type ApplyResult } from "@/lib/api";
import { cn } from "@/lib/utils";

/** Colour one diff line by its leading marker (context / add / remove / header). */
function diffLineClass(line: string): string {
  if (line.startsWith("+++") || line.startsWith("---")) return "text-[var(--fg-soft)] font-semibold";
  if (line.startsWith("@@")) return "text-[var(--accent)] font-semibold";
  if (line.startsWith("+")) return "bg-[var(--success)]/10 text-[var(--success)]";
  if (line.startsWith("-")) return "bg-[var(--danger)]/10 text-[var(--danger)]";
  return "text-[var(--fg-muted)]";
}

function StatusBadge({ status }: { status: string }) {
  if (status === "APPROVED") return <Badge variant="success" className="text-[10px]">موافَق عليه</Badge>;
  if (status === "REJECTED") return <Badge variant="danger" className="text-[10px]">مرفوض</Badge>;
  return <Badge variant="warn" className="text-[10px]">بانتظار قرارك</Badge>;
}

/**
 * Review a code patch the agent proposed, then approve → apply → (if needed) revert.
 *
 * The agent can only ever *propose*; this dialog is the human gate that decides
 * whether the change lands. Nothing is written until Apply runs, and Apply only
 * runs on an APPROVED row, on a dedicated git branch.
 */
export function CodePatchDialog({
  approvalId, open, onOpenChange, onResolved,
}: {
  approvalId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onResolved?: () => void;
}) {
  const [detail, setDetail] = useState<ApprovalDetail | null>(null);
  const [applied, setApplied] = useState<ApplyResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState<"approve" | "reject" | "apply" | "revert" | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !approvalId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setApplied(null);
    apiGet.approvalDetail(approvalId)
      .then((d) => {
        if (cancelled) return;
        setDetail(d);
        setApplied((d.result as ApplyResult) ?? null);
      })
      .catch((e: unknown) => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [open, approvalId]);

  async function run(kind: "approve" | "reject" | "apply" | "revert") {
    if (!approvalId) return;
    setBusy(kind);
    setError(null);
    try {
      if (kind === "apply") {
        setApplied(await apiCode.apply(approvalId));
      } else if (kind === "revert") {
        await apiCode.revert(approvalId);
        setApplied(null);
      } else {
        await apiPost.resolveApproval(approvalId, kind === "approve" ? "APPROVED" : "REJECTED");
        setDetail(await apiGet.approvalDetail(approvalId));
      }
      onResolved?.();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  const status = (detail?.status || "PENDING").toUpperCase();
  const payload = (detail?.payload || {}) as Record<string, any>;
  const diff: string = detail?.diff || payload.diff || "";
  const files: string[] = detail?.files || payload.files || [];
  const summary: string = detail?.summary || payload.summary || "";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <FileCode2 className="h-4 w-4 text-[var(--accent)]" />
            <DialogTitle>مراجعة تعديل الكود</DialogTitle>
            <StatusBadge status={status} />
          </div>
          <DialogDescription>
            الوكيل اقترح التعديل ده — مفيش أي ملف اتغيّر لحد دلوقتي. راجع الـdiff
            ووافق، وبعدها اضغط تطبيق ليُنفّذ على فرع git منفصل (main مش بيتلمس).
          </DialogDescription>
        </DialogHeader>

        {loading && (
          <div className="flex justify-center py-10">
            <Spinner />
          </div>
        )}

        {error && (
          <div className="flex items-start gap-2 rounded-xl border border-[var(--danger)]/40 bg-[color-mix(in_srgb,var(--danger)_8%,transparent)] p-3 text-[12px] text-[var(--danger)]">
            <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        {!loading && (
          <div className="space-y-4">
            {summary && (
              <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3">
                <div className="text-[11px] text-[var(--fg-soft)] mb-1">الملخص</div>
                <div className="text-[13px] text-[var(--fg)]">{summary}</div>
              </div>
            )}

            {files.length > 0 && (
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[11px] text-[var(--fg-soft)]">الملفات:</span>
                {files.map((f) => (
                  <Badge key={f} variant="default" className="text-[10px] font-mono" dir="ltr">
                    {f}
                  </Badge>
                ))}
              </div>
            )}

            {diff ? (
              <div className="rounded-xl border border-[var(--border)] overflow-hidden">
                <div className="flex items-center gap-2 px-3 py-2 bg-[var(--surface-2)] border-b border-[var(--border)]">
                  <FileCode2 className="h-3.5 w-3.5 text-[var(--fg-soft)]" />
                  <span className="text-[11px] text-[var(--fg-muted)]">الفرق (diff)</span>
                </div>
                <pre
                  dir="ltr"
                  className="max-h-[45vh] overflow-auto p-3 text-[11px] leading-5 font-mono bg-[var(--surface)]"
                >
                  {diff.split("\n").map((line, i) => (
                    <div key={i} className={cn("px-1", diffLineClass(line))}>{line || " "}</div>
                  ))}
                </pre>
              </div>
            ) : (
              <div className="text-[12px] text-[var(--fg-soft)]">لا يوجد diff معروض لهذا الاقتراح.</div>
            )}

            {applied && (
              <div className="rounded-xl border border-[var(--success)]/40 bg-[color-mix(in_srgb,var(--success)_8%,transparent)] p-3 space-y-1.5">
                <div className="flex items-center gap-2 text-[12px] text-[var(--success)] font-medium">
                  <ShieldCheck className="h-4 w-4" />
                  تم التطبيق على فرع منفصل
                </div>
                <div className="flex items-center gap-2 text-[11px] text-[var(--fg-muted)]">
                  <GitBranch className="h-3.5 w-3.5" />
                  <span className="font-mono" dir="ltr">{applied.branch || "—"}</span>
                  {applied.commit && <span className="font-mono" dir="ltr">@{applied.commit}</span>}
                </div>
                {applied.undo && (
                  <div className="text-[11px] text-[var(--fg-soft)] font-mono" dir="ltr">
                    undo: {applied.undo}
                  </div>
                )}
              </div>
            )}

            <div className="flex flex-wrap items-center justify-end gap-2 pt-1">
              {status === "PENDING" && (
                <>
                  <Button
                    variant="outline" size="sm" loading={busy === "reject"}
                    onClick={() => run("reject")} disabled={busy !== null}
                  >
                    رفض
                  </Button>
                  <Button
                    variant="primary" size="sm" loading={busy === "approve"}
                    onClick={() => run("approve")} disabled={busy !== null}
                  >
                    <Check className="h-3.5 w-3.5" />
                    موافقة
                  </Button>
                </>
              )}

              {status === "APPROVED" && !applied && (
                <Button
                  variant="primary" size="sm" loading={busy === "apply"}
                  onClick={() => run("apply")} disabled={busy !== null}
                >
                  <ShieldCheck className="h-3.5 w-3.5" />
                  تطبيق على فرع جديد
                </Button>
              )}

              {status === "APPROVED" && applied && (
                <Button
                  variant="outline" size="sm" loading={busy === "revert"}
                  onClick={() => run("revert")} disabled={busy !== null}
                >
                  <RotateCcw className="h-3.5 w-3.5" />
                  تراجع
                </Button>
              )}

              <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)} disabled={busy !== null}>
                إغلاق
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
