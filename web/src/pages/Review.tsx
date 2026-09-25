/**
 * Review board — stage 3 as a dedicated page: every candidate with its WHY,
 * the open data conflicts (resolvable by hand, winner becomes VERIFIED), and
 * the full ReviewPanel (facts + decisions) on selection.
 */
import { useState } from "react";
import { ShieldAlert, Loader2, CheckCircle2, Eye, EyeOff, Search, AlertTriangle } from "lucide-react";
import { Card, CardContent } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { useLiveData } from "@/hooks/useLiveData";
import { apiGet, apiGetExtra, apiPostExtra, type Presentation } from "@/lib/api";
import { friendlyError } from "@/lib/friendly";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState, Spinner } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { StaleBanner } from "@/components/ui/StaleBanner";
import { ReviewPanel } from "@/components/review/ReviewPanel";
import { cn, truncate } from "@/lib/utils";
import { toast } from "sonner";

export function ReviewPage() {
  const { data, loading, error, refresh } = useLiveData(
    () => apiGet.reviewPending(), 8000
  );
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showConflicts, setShowConflicts] = useState(true);
  const leads = data?.leads || [];
  const selected = leads.find((l) => l.lead.lead_id === selectedId) || null;

  // conflicts that belong to the pending subjects — one fetch, filtered client-side
  const { data: conflictData, refresh: refreshConflicts } = useLiveData(
    () => apiGetExtra.conflicts("OPEN"), 15000
  );
  const conflicts = conflictData?.conflicts || [];
  const subjectIds = new Set(leads.map((l) => l.subject.id));
  const relevantConflicts = conflicts.filter((c) => subjectIds.has(c.subject_id));
  // fact_id -> human-readable value, harvested from the loaded presentations
  // (current value + alternatives) so the human decides on VALUES, not ids
  const factLabels: Record<string, { value: string; status: string }> = {};
  for (const p of leads) {
    for (const node of Object.values(p.facts_snapshot.fields)) {
      factLabels[node.fact_id] = { value: node.value, status: node.status };
      for (const alt of node.alternatives || []) {
        factLabels[alt.fact_id] = { value: alt.value, status: alt.status };
      }
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        icon={<ShieldAlert className="h-5 w-5" />}
        title="لوحة المراجعة"
        description="كل عميل معله السبب والأدلة والنواقص — القرار النهائي بيدك، ومفيش أي إرسال تلقائي"
      />

      {error && data && (
        <StaleBanner error={error} subject="قائمة المراجعة" onRetry={() => void refresh()} />
      )}

      {relevantConflicts.length > 0 && (
        <ConflictBanner conflicts={relevantConflicts} factLabels={factLabels}
                        onResolved={() => { refreshConflicts(); refresh(); }} />
      )}

      {error && !data ? (
        <ErrorState error={error} onRetry={() => void refresh()} subject="قائمة المراجعة" />
      ) : loading && !data ? <Spinner /> : leads.length === 0 ? (
        <EmptyState icon={<Search className="h-8 w-8" />} title="لا يوجد مرشحون بانتظار المراجعة"
                    description="شغّل مهمة بحث من صفحة مهام البحث — أول ما تخلص هتلاقي النتائج هنا بالأسباب." />
      ) : (
        <div className="grid lg:grid-cols-[minmax(300px,1fr)_2fr] gap-4">
          <div className="space-y-2">
            {leads.map((p) => (
              <button key={p.lead.lead_id} onClick={() => setSelectedId(p.lead.lead_id)}
                className={cn("w-full text-start rounded-xl border p-3 transition-colors",
                  selectedId === p.lead.lead_id
                    ? "border-[var(--accent)] bg-[color-mix(in_srgb,var(--accent)_8%,transparent)]"
                    : "border-[var(--border-soft)] bg-[var(--bg-elev)] hover:border-[var(--accent)]/50")}>
                <div className="flex items-center gap-2">
                  <span className="text-[15px] font-bold tnum">{p.fit.fit_score ?? "—"}</span>
                  {p.fit.tier && <Badge variant={p.fit.tier.toUpperCase().startsWith("A") ? "success" : p.fit.tier.toUpperCase().startsWith("B") ? "warn" : "default"}>{p.fit.tier}</Badge>}
                  {p.conflicts.length > 0 && (
                    <Badge variant="danger" className="text-[10px]">{p.conflicts.length} تعارض</Badge>
                  )}
                  {p.lead.disposition && (
                    <Badge variant={p.lead.disposition === "APPROVE_CONTACT" ? "success" : p.lead.disposition === "REJECT" ? "danger" : "info"} className="text-[10px]">
                      {DECISION_SHORT[p.lead.disposition]}
                    </Badge>
                  )}
                  <span className="ms-auto text-[10px] text-[var(--fg-soft)]">{p.subject.id}</span>
                </div>
                <div className="text-[13px] font-semibold mt-1 truncate">
                  {p.identity.name?.value || p.subject.id}
                </div>
                <div className="text-[11.5px] text-[var(--fg-muted)] mt-0.5 leading-4">
                  {p.fit.why[0] ? truncate(p.fit.why[0], 70) : "—"}
                </div>
                {/* prototype pattern: the lead's facts WITH their evidence inline */}
                <div className="space-y-1 mt-2">
                  {Object.entries(p.facts_snapshot.fields).slice(0, 3).map(([field, node]) => (
                    <div key={node.fact_id} className="flex items-start gap-1.5 text-[11px]">
                      {node.status === "VERIFIED"
                        ? <CheckCircle2 size={11} className="text-emerald-500 mt-0.5 shrink-0" />
                        : node.status === "CONFLICTED"
                          ? <ShieldAlert size={11} className="text-rose-500 mt-0.5 shrink-0" />
                          : <AlertTriangle size={11} className="text-amber-500 mt-0.5 shrink-0" />}
                      <span className="text-[var(--fg-muted)]">
                        <span className="font-medium text-[var(--fg)]">{node.value}</span>
                        {node.sources[0]?.source_url && (
                          <> — <a href={node.sources[0].source_url} target="_blank" rel="noopener"
                                  className="underline decoration-dotted hover:text-[var(--accent)]">
                            {truncate(node.sources[0].source_url.replace(/^https?:\/\//, ""), 34)}</a></>
                        )}
                      </span>
                    </div>
                  ))}
                </div>
              </button>
            ))}
          </div>

          {selected ? (
            <Card>
              <CardContent className="p-4">
                <ReviewPanel leadId={selected.lead.lead_id!} onChanged={refresh} />
              </CardContent>
            </Card>
          ) : (
            <Card><CardContent className="p-6 text-center text-[13px] text-[var(--fg-muted)]">
              اختر عميل من القائمة لعرض طبقة التفسير الكاملة
            </CardContent></Card>
          )}
        </div>
      )}
    </div>
  );
}

/** Open conflicts for the pending subjects — the human sees BOTH values and
 * picks the winner: winner -> VERIFIED, loser -> STALE (never deleted). */
function ConflictBanner({ conflicts, factLabels, onResolved }: {
  conflicts: Awaited<ReturnType<typeof apiGetExtra.conflicts>>["conflicts"];
  factLabels: Record<string, { value: string; status: string }>;
  onResolved: () => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(true);

  async function resolve(conflictId: string, winnerFactId: string) {
    setBusy(conflictId + winnerFactId);
    try {
      await apiPostExtra.conflictResolve(conflictId, winnerFactId, "قرار بشري من لوحة المراجعة");
      toast.success("انحل التعارض — القيمة الرابحة بقت VERIFIED والتانية STALE");
      onResolved();
    } catch (e) {
      toast.error(friendlyError(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card className="border-rose-500/40">
      <CardContent className="p-4 space-y-3">
        <button className="w-full flex items-center gap-2" onClick={() => setExpanded(!expanded)}>
          <ShieldAlert className="h-4 w-4 text-rose-500" />
          <span className="text-[13px] font-bold">تعارضات بيانات مفتوحة ({conflicts.length})</span>
          <span className="text-[11px] text-[var(--fg-muted)]">— اختار القيمة الصحيحة؛ الخسارة تبقى STALE موثقة مش محذوفة</span>
          {expanded ? <EyeOff className="h-3.5 w-3.5 ms-auto" /> : <Eye className="h-3.5 w-3.5 ms-auto" />}
        </button>
        {expanded && conflicts.slice(0, 6).map((c) => (
          <div key={c.conflict_id} className="rounded-lg border border-[var(--border-soft)] p-2.5 space-y-1.5">
            <div className="text-[11px] text-[var(--fg-muted)]">
              <span className="font-semibold text-[var(--fg)]">{c.subject_id}</span> — الحقل: {c.field}
            </div>
            <div className="grid sm:grid-cols-2 gap-2">
              {([c.fact_a, c.fact_b] as const).map((fid) => {
                const label = factLabels[fid]?.value || fid;
                return (
                  <Button key={fid} variant="outline" disabled={busy != null}
                          onClick={() => resolve(c.conflict_id, fid)}
                          className="text-[12px] h-9 justify-start">
                    {busy === c.conflict_id + fid
                      ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      : <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />}
                    <span className="truncate" dir="auto">{label}</span>
                  </Button>
                );
              })}
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

const DECISION_SHORT: Record<string, string> = {
  APPROVE_CONTACT: "معتمد", REJECT: "مستبعد",
  RESEARCH_MORE: "بحث أعمق", SAVE_FOR_LATER: "لاحقًا",
};
