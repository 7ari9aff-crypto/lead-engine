import { useCallback, useEffect, useState } from "react";
import { Zap, Rocket, GitBranch, ShieldCheck, Loader2 } from "lucide-react";

import { PageHeader } from "@/components/layout/PageHeader";
import { Card, CardContent } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { useLiveData } from "@/hooks/useLiveData";
import { v6Api, type V6Job, type V6Lead, type V6Lineage } from "@/lib/v6api";

type Tab = "campaigns" | "review" | "leads";

const STATE_COLORS: Record<string, string> = {
  READY_FOR_REVIEW: "text-[var(--warn)]",
  APPROVED: "text-emerald-400",
  REJECTED: "text-red-400",
};

function stateLabel(state: string): string {
  return {
    QUEUED: "في الطابور",
    PLANNING: "تخطيط",
    DISCOVERING: "اكتشاف",
    ENRICHING: "إثراء",
    VERIFYING: "تحقق",
    SCORING: "تقييم",
    QUALIFYING: "تأهيل",
    READY_FOR_REVIEW: "بانتظار المراجعة",
    PARTIAL_SUCCESS: "نجاح جزئي",
    FAILED: "فاشلة",
    CANCELLED: "ملغاة",
    PAUSED: "موقوفة",
  }[state] || state;
}

export function V6ConsolePage() {
  const [tab, setTab] = useState<Tab>("review");
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [lineage, setLineage] = useState<{ leadId: string; data: V6Lineage } | null>(null);
  const [pii, setPii] = useState<Record<string, { email?: string; phone?: string; name?: string }>>({});

  const jobs = useLiveData(() => v6Api.jobs(), 6000);
  const pending = useLiveData(() => v6Api.pending(), 6000);
  const leads = useLiveData(() => v6Api.leads(), 8000);

  const decide = useCallback(async (leadId: string, approve: boolean) => {
    setBusy(leadId);
    setNotice(null);
    try {
      const out = await v6Api.decide(leadId, approve, approve ? "approved from V6 console" : "");
      setNotice(approve ? `تم الاعتماد — الحالة: ${out.state}` : "تم الرفض");
      await pending.refresh();
      await leads.refresh();
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "فشل القرار");
    } finally {
      setBusy(null);
    }
  }, [pending, leads]);

  const showLineage = useCallback(async (leadId: string) => {
    setBusy(leadId);
    try {
      const data = await v6Api.lineage(leadId);
      setLineage({ leadId, data });
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "فشل الـ lineage");
    } finally {
      setBusy(null);
    }
  }, []);

  const reveal = useCallback(async (lead: V6Lead) => {
    setBusy(lead.id);
    try {
      const purpose = lead.state === "APPROVED" ? "outreach" : "human_review";
      const out = await v6Api.revealPii(lead.id, purpose);
      setPii((prev) => ({ ...prev, [lead.id]: out }));
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "فشل كشف البيانات");
    } finally {
      setBusy(null);
    }
  }, []);

  useEffect(() => { setNotice(null); }, [tab]);

  return (
    <div className="space-y-5">
      <PageHeader
        icon={<Zap className="h-5 w-5 text-white" />}
        title="محرك V6"
        description="المعمارية الجديدة: PostgreSQL مصدر الحقيقة، مهام دائمة بـ checkpoints، وPII مقفول بالخزنة"
        action={<Button variant="outline" size="sm" onClick={() => { void jobs.refresh(); void pending.refresh(); void leads.refresh(); }}>
          <Loader2 className="h-4 w-4" /> تحديث
        </Button>}
      />

      {notice && (
        <div className="rounded-xl border border-[var(--accent)]/30 bg-[var(--accent)]/5 px-4 py-2.5 text-sm">
          {notice}
        </div>
      )}

      <div className="flex gap-2">
        {([["review", "بانتظار المراجعة"], ["leads", "كل العملاء"], ["campaigns", "المهام"]] as [Tab, string][]).map(([key, label]) => (
          <Button key={key} variant={tab === key ? "primary" : "outline"} size="sm"
                  onClick={() => setTab(key)}>
            {label}
          </Button>
        ))}
      </div>

      {tab === "campaigns" && <JobsPanel jobs={jobs.data} loading={jobs.loading} error={jobs.error} />}
      {tab === "review" && <ReviewPanel pending={pending.data} loading={pending.loading}
                                        error={pending.error} busy={busy}
                                        onDecide={decide} onLineage={showLineage}
                                        pii={pii} onReveal={reveal} />}
      {tab === "leads" && <LeadsPanel leads={leads.data} loading={leads.loading}
                                      error={leads.error} busy={busy}
                                      onDecide={decide} onLineage={showLineage}
                                      pii={pii} onReveal={reveal} />}

      {lineage && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4"
             onClick={() => setLineage(null)}>
          <div className="bg-[var(--bg)] rounded-2xl border border-[var(--border-soft)] max-w-2xl w-full max-h-[80vh] overflow-y-auto p-5"
               onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-bold flex items-center gap-2">
                <GitBranch className="h-4 w-4" /> لينياج العميل — ليه موجود؟
              </h3>
              <Button variant="ghost" size="sm" onClick={() => setLineage(null)}>إغلاق</Button>
            </div>
            <div className="space-y-3 text-sm">
              <Section title="القرار">
                {(lineage.data.qualification[0]?.reasons || []).join(" · ") || "—"}
              </Section>
              <Section title="الدرجة">
                {lineage.data.scores[0]?.score ?? "—"} (v{lineage.data.scores[0]?.score_version || "?"})
                {" — "}{(lineage.data.scores[0]?.explanations || []).join(" · ")}
              </Section>
              <Section title="المصادر">
                {(lineage.data.sources || []).map((s) => (
                  <div key={s.id} className="truncate">
                    <span className="text-[var(--fg-muted)]">{s.provider_id || s.kind}:</span>{" "}
                    {s.url || "—"}
                  </div>
                ))}
              </Section>
              <Section title="التحقق">
                {(lineage.data.verifications || []).map((v, i) => (
                  <div key={i}>{v.status} عبر {v.provider_id || "—"}</div>
                ))}
              </Section>
              <Section title="نداءات المزودين">
                {(lineage.data.provider_calls || []).map((c, i) => (
                  <div key={i}>{c.provider_id} · {c.operation} · {c.status}</div>
                ))}
              </Section>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-[var(--border-soft)] p-3">
      <div className="text-[11px] uppercase tracking-wide text-[var(--fg-muted)] mb-1">{title}</div>
      <div className="space-y-1">{children || "—"}</div>
    </div>
  );
}

function JobsPanel({ jobs, loading, error }: {
  jobs: V6Job[] | null; loading: boolean; error: Error | null;
}) {
  if (loading && !jobs) return <Spinner />;
  if (error && !jobs) return <ErrorState error={error} subject="مهام V6" onRetry={() => {}} />;
  return (
    <Card>
      <CardContent className="p-0 divide-y divide-[var(--border-soft)]">
        {(jobs || []).map((j) => (
          <div key={j.id} className="flex items-center justify-between px-4 py-3 text-sm">
            <div>
              <div className="font-medium">{j.job_type}</div>
              <div className="text-xs text-[var(--fg-muted)]">
                {j.attempts}/{j.max_attempts} محاولات · {new Date(j.created_at).toLocaleString("ar")}
                {j.last_error ? ` · ${j.last_error.slice(0, 80)}` : ""}
              </div>
            </div>
            <span className={`font-semibold ${STATE_COLORS[j.state] || ""}`}>
              {stateLabel(j.state)}
            </span>
          </div>
        ))}
        {(!jobs || jobs.length === 0) && (
          <div className="px-4 py-8 text-center text-sm text-[var(--fg-muted)]">
            مفيش مهام V6 بعد — أنشئ حملة من الـ API أو الشات.
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function LeadRow({ lead, busy, onDecide, onLineage, pii, onReveal }: {
  lead: V6Lead; busy: string | null;
  onDecide: (id: string, approve: boolean) => void;
  onLineage: (id: string) => void;
  pii: Record<string, { email?: string; phone?: string; name?: string }>;
  onReveal: (lead: V6Lead) => void;
}) {
  const revealed = pii[lead.id];
  return (
    <div className="px-4 py-3">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="min-w-0">
          <div className="font-medium truncate">
            {lead.display.name || lead.display.domain || "—"}
            <span className="text-xs text-[var(--fg-muted)] ms-2">
              {lead.display.city || ""} {lead.display.industry || ""}
            </span>
          </div>
          <div className="text-xs text-[var(--fg-muted)] truncate">
            {lead.display.domain || "—"} · بريد: {lead.masked_email || "—"}
            ({lead.email_status || "?"}) · هاتف: {lead.masked_phone || "—"} · درجة {lead.score ?? "—"}
          </div>
          {revealed && (
            <div className="text-xs mt-1 text-emerald-400">
              {revealed.name ? `${revealed.name} — ` : ""}
              {revealed.email || ""}{revealed.phone ? ` · ${revealed.phone}` : ""}
              <span className="text-[var(--fg-muted)]"> (كشف مُدقَّق بغرض {lead.state === "APPROVED" ? "outreach" : "human_review"})</span>
            </div>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className={`text-xs font-semibold ${STATE_COLORS[lead.state] || ""}`}>
            {stateLabel(lead.state)} · {lead.decision || ""}
          </span>
          <Button variant="ghost" size="sm" disabled={busy === lead.id}
                  onClick={() => onLineage(lead.id)}>لينياج</Button>
          <Button variant="ghost" size="sm" disabled={busy === lead.id}
                  onClick={() => onReveal(lead)}>
            <ShieldCheck className="h-3.5 w-3.5" /> كشف
          </Button>
          {lead.state === "READY_FOR_REVIEW" && (
            <>
              <Button size="sm" disabled={busy === lead.id}
                      onClick={() => onDecide(lead.id, true)}>اعتماد</Button>
              <Button variant="outline" size="sm" disabled={busy === lead.id}
                      onClick={() => onDecide(lead.id, false)}>رفض</Button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function ReviewPanel({ pending, loading, error, busy, onDecide, onLineage, pii, onReveal }: {
  pending: V6Lead[] | null; loading: boolean; error: Error | null; busy: string | null;
  onDecide: (id: string, approve: boolean) => void;
  onLineage: (id: string) => void;
  pii: Record<string, { email?: string; phone?: string; name?: string }>;
  onReveal: (lead: V6Lead) => void;
}) {
  if (loading && !pending) return <Spinner />;
  if (error && !pending) return <ErrorState error={error} subject="قائمة المراجعة" onRetry={() => {}} />;
  return (
    <Card>
      <CardContent className="p-0 divide-y divide-[var(--border-soft)]">
        {(pending || []).map((l) => (
          <LeadRow key={l.id} lead={l} busy={busy} onDecide={onDecide}
                   onLineage={onLineage} pii={pii} onReveal={onReveal} />
        ))}
        {(!pending || pending.length === 0) && (
          <div className="px-4 py-10 text-center">
            <Rocket className="h-6 w-6 mx-auto mb-2 text-[var(--fg-muted)]" />
            <p className="text-sm text-[var(--fg-muted)]">
              مفيش عملاء بانتظار المراجعة — شغّل حملة وستظهر هنا بعد اكتمال الخط.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function LeadsPanel({ leads, loading, error, busy, onDecide, onLineage, pii, onReveal }: {
  leads: V6Lead[] | null; loading: boolean; error: Error | null; busy: string | null;
  onDecide: (id: string, approve: boolean) => void;
  onLineage: (id: string) => void;
  pii: Record<string, { email?: string; phone?: string; name?: string }>;
  onReveal: (lead: V6Lead) => void;
}) {
  if (loading && !leads) return <Spinner />;
  if (error && !leads) return <ErrorState error={error} subject="العملاء" onRetry={() => {}} />;
  return (
    <Card>
      <CardContent className="p-0 divide-y divide-[var(--border-soft)]">
        {(leads || []).map((l) => (
          <LeadRow key={l.id} lead={l} busy={busy} onDecide={onDecide}
                   onLineage={onLineage} pii={pii} onReveal={onReveal} />
        ))}
        {(!leads || leads.length === 0) && (
          <div className="px-4 py-10 text-center text-sm text-[var(--fg-muted)]">
            مفيش عملاء بعد.
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function Spinner() {
  return (
    <div className="flex items-center justify-center py-16 text-[var(--fg-muted)]">
      <Loader2 className="h-5 w-5 animate-spin" />
    </div>
  );
}

export default V6ConsolePage;
