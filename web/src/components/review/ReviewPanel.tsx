/**
 * Stage 3 review panel — the interpretation layer for one lead (directive §26):
 * fit + why + verification + conflicts + missing info + freshness + sources,
 * and THE four human decisions (§27). APPROVE_CONTACT is terminal: nothing
 * sends, ever (§45).
 */
import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  BadgeCheck,
  CheckCircle2,
  Clock,
  FileSearch,
  HelpCircle,
  Loader2,
  ShieldAlert,
  ThumbsDown,
  Bookmark,
  Send,
  Search,
} from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { apiGet, apiPost, type Presentation } from "@/lib/api";
import { friendlyError } from "@/lib/friendly";
import { toast } from "sonner";

const STATUS_STYLES: Record<string, string> = {
  VERIFIED: "text-emerald-600 dark:text-emerald-400",
  UNVERIFIED: "text-amber-600 dark:text-amber-400",
  CONFLICTED: "text-rose-600 dark:text-rose-400",
  STALE: "text-zinc-500",
  INFERRED: "text-violet-600 dark:text-violet-400",
};

const STATUS_AR: Record<string, string> = {
  VERIFIED: "موثقة",
  UNVERIFIED: "بمصدر واحد",
  CONFLICTED: "متضاربة",
  STALE: "قديمة",
  INFERRED: "استنتاج",
};

const FIELD_AR: Record<string, string> = {
  phone: "الهاتف", email: "البريد", city: "المدينة", country: "الدولة",
  domain: "الدومين", name: "الاسم", branches: "الفروع",
  employee_count: "عدد الموظفين", decision_maker: "صانع القرار",
  industry: "القطاع", website: "الموقع", linkedin: "لينكدإن",
};

export function ReviewPanel({ leadId, onChanged }: { leadId: string; onChanged?: () => void }) {
  const [data, setData] = useState<Presentation | null>(null);
  const [loading, setLoading] = useState(true);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [childJob, setChildJob] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await apiGet.leadPresentation(leadId));
    } catch (e) {
      toast.error(friendlyError(e));
    } finally {
      setLoading(false);
    }
  }, [leadId]);

  useEffect(() => { load(); }, [load]);

  async function decide(action: "APPROVE_CONTACT" | "REJECT" | "RESEARCH_MORE" | "SAVE_FOR_LATER") {
    setBusy(action);
    try {
      const res = await apiPost.leadDecision(leadId, action, note || undefined);
      if (action === "RESEARCH_MORE" && res.child_job_id) {
        setChildJob(res.child_job_id);
        toast.success("بدأت مهمة بحث أعمق بنفس السياق — تابعها في صفحة المهام");
      } else if (action === "APPROVE_CONTACT") {
        toast.success("تم الاعتماد — ده آخر إجراء في النظام، مفيش أي إرسال تلقائي");
      } else {
        toast.success("تم تسجيل قرارك");
      }
      setNote("");
      await load();
      onChanged?.();
    } catch (e) {
      toast.error(friendlyError(e));
    } finally {
      setBusy(null);
    }
  }

  if (loading) {
    return <div className="flex items-center gap-2 py-6 justify-center text-[var(--fg-muted)] text-[13px]">
      <Loader2 className="h-4 w-4 animate-spin" /> جارٍ تحميل طبقة التفسير…
    </div>;
  }
  if (!data) {
    return <div className="py-4 text-[13px] text-[var(--fg-muted)] text-center">
      لا توجد طبقة تفسير لهذا الـlead (من تشغيل قديم).
    </div>;
  }

  const d = data.lead.disposition;
  return (
    <section className="space-y-4">
      <h3 className="text-[12px] font-semibold text-[var(--fg-soft)] flex items-center gap-1.5">
        <FileSearch className="h-3.5 w-3.5" /> طبقة التفسير — ليه العميل ده؟
      </h3>

      {/* Fit + why */}
      <div className="rounded-xl border border-[var(--border-soft)] bg-[var(--bg-soft)] p-3 space-y-2">
        <div className="flex items-center gap-2">
          <span className="text-[20px] font-bold tnum">{data.fit.fit_score ?? "—"}</span>
          {data.fit.tier && <Badge variant={data.fit.tier.toUpperCase().startsWith("A") ? "success" : data.fit.tier.toUpperCase().startsWith("B") ? "warn" : "default"}>
            {data.fit.tier.toUpperCase().startsWith("A") ? "ممتاز" : data.fit.tier.toUpperCase().startsWith("B") ? "جيد" : "عادي"}
          </Badge>}
          {data.fit.confidence != null && (
            <span className="text-[11px] text-[var(--fg-soft)] tnum">ثقة {(data.fit.confidence * 100).toFixed(0)}%</span>
          )}
          <span className="ms-auto text-[10px] text-[var(--fg-soft)]">
            {data.fit.deterministic ? "قرار حتمي من القواعد" : "تقييم مسنود بالأدلة"}
          </span>
        </div>
        {data.fit.why.length > 0 && (
          <ul className="space-y-1">
            {data.fit.why.map((w, i) => (
              <li key={i} className="text-[12.5px] leading-5 flex gap-1.5">
                <span className="text-[var(--accent)]">•</span>{w}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Conflicts */}
      {data.conflicts.length > 0 && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/5 p-3 space-y-1.5">
          <div className="text-[12px] font-semibold text-rose-600 dark:text-rose-400 flex items-center gap-1.5">
            <ShieldAlert className="h-3.5 w-3.5" /> تعارضات بيانات ({data.conflicts.length})
          </div>
          <div className="text-[11.5px] text-[var(--fg-muted)] leading-5">
            حقول فيها قيمتان متناقضتان من مصدرين — محتاجة تحقيق أو قرار منك.
          </div>
        </div>
      )}

      {/* Facts with status */}
      <div className="space-y-1.5">
        <div className="text-[11px] font-semibold text-[var(--fg-soft)]">
          الحقائق المخزنة ({Object.keys(data.facts_snapshot.fields).length}) — مصادر: {data.sources_count}
        </div>
        {Object.entries(data.facts_snapshot.fields).map(([field, node]) => (
          <div key={node.fact_id} className="flex items-center gap-2 rounded-lg border border-[var(--border-soft)] px-2.5 py-1.5">
            <span className="text-[11px] text-[var(--fg-muted)] shrink-0">{FIELD_AR[field] || field}</span>
            <span className="text-[12.5px] font-medium truncate" dir="auto">{node.value}</span>
            <span className={`ms-auto text-[10px] font-semibold shrink-0 ${STATUS_STYLES[node.status] || ""}`}>
              {STATUS_AR[node.status] || node.status}
            </span>
          </div>
        ))}
      </div>

      {/* Missing / stale */}
      {(data.missing_information.length > 0) && (
        <div className="flex flex-wrap gap-1.5 items-center">
          <HelpCircle className="h-3.5 w-3.5 text-[var(--fg-soft)]" />
          <span className="text-[11px] text-[var(--fg-soft)]">نواقص/غير مؤكد:</span>
          {data.missing_information.map((m) => (
            <Badge key={m} variant="default" className="text-[10px]">{FIELD_AR[m] || m}</Badge>
          ))}
        </div>
      )}

      <div className="flex items-center gap-3 text-[11px] text-[var(--fg-soft)]">
        <span className="flex items-center gap-1"><BadgeCheck className="h-3.5 w-3.5" />حقائق موثقة: {data.verification.verified_facts}</span>
        {data.stale_fields.length > 0 && (
          <span className="flex items-center gap-1"><Clock className="h-3.5 w-3.5" />قديمة: {data.stale_fields.map((f) => FIELD_AR[f] || f).join("، ")}</span>
        )}
      </div>

      {/* The human decision — §27 */}
      <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-soft)] p-3 space-y-2.5">
        <div className="text-[12px] font-semibold flex items-center gap-1.5">
          <CheckCircle2 className="h-3.5 w-3.5 text-[var(--accent)]" /> قرارك (القرار النهائي بيدك)
        </div>
        {d && (
          <div className="text-[11.5px] text-[var(--fg-muted)]">
            القرار الحالي: <span className="font-bold text-[var(--fg)]">{DECISION_AR[d]}</span>
          </div>
        )}
        <Input value={note} onChange={(e) => setNote(e.target.value)}
               placeholder="ملاحظة (اختياري) — مثال: دور أكتر على الإيميل" className="text-[13px]" />
        <div className="grid grid-cols-2 gap-2">
          <Button variant="primary" disabled={busy != null} onClick={() => decide("APPROVE_CONTACT")}
                  className="text-[12px] h-9">
            {busy === "APPROVE_CONTACT" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
            اعتمد للتواصل
          </Button>
          <Button variant="outline" disabled={busy != null} onClick={() => decide("RESEARCH_MORE")}
                  className="text-[12px] h-9">
            {busy === "RESEARCH_MORE" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-3.5 w-3.5" />}
            ابحث أكتر
          </Button>
          <Button variant="outline" disabled={busy != null} onClick={() => decide("SAVE_FOR_LATER")}
                  className="text-[12px] h-9">
            {busy === "SAVE_FOR_LATER" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Bookmark className="h-3.5 w-3.5" />}
            خزّن لاحقًا
          </Button>
          <Button variant="danger" disabled={busy != null} onClick={() => decide("REJECT")}
                  className="text-[12px] h-9">
            {busy === "REJECT" ? <Loader2 className="h-4 w-4 animate-spin" /> : <ThumbsDown className="h-3.5 w-3.5" />}
            استبعد
          </Button>
        </div>
        {childJob && (
          <div className="text-[11.5px] text-[var(--accent)] flex items-center gap-1.5">
            <AlertTriangle className="h-3.5 w-3.5" /> مهمة البحث الأعمق: {childJob}
          </div>
        )}
        <p className="text-[10px] text-[var(--fg-soft)] leading-4">
          اعتماد التواصل هو آخر خطوة في النظام الحالي — لا يوجد أي إرسال تلقائي.
        </p>
      </div>
    </section>
  );
}

const DECISION_AR: Record<string, string> = {
  APPROVE_CONTACT: "معتمد للتواصل",
  REJECT: "مستبعد",
  RESEARCH_MORE: "بحث أعمق",
  SAVE_FOR_LATER: "خزّن لاحقًا",
};
