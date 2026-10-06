import React, { useState } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import { cn } from "@/lib/utils";
import { useLeadEngine } from "@/lib/leadEngine/store";
import { hasContact, fmtNum, tr } from "@/lib/leadEngine/format";
import { eventLabel } from "@/lib/leadEngine/i18n";
import { PageHeader } from "@/components/leadEngine/PageHeader";
import { StatusBadge, ScoreRing, MatchGlyph, TimeAgo, Pill } from "@/components/leadEngine/primitives";
import { ArrowLeft, Eye, ExternalLink, CheckCircle2, XCircle, Clock, AlertTriangle, FileSearch, Check, Minus } from "lucide-react";

export default function LeadDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const { t, lang, leads, jobs, icps, reviewLead, revealPII, researchMore, canFindContacts } = useLeadEngine();
  const ar = lang === "ar";
  const lead = leads.find((l) => l.id === id);
  const [showPiiForm, setShowPiiForm] = useState(false);
  const [piiReason, setPiiReason] = useState("");
  const [note, setNote] = useState("");

  const back = () => (location.key === "default" ? navigate("/leads") : navigate(-1));

  if (!lead) {
    return (
      <div className="px-8 py-20 text-center">
        <p className="text-muted-foreground">{ar ? "العميل غير موجود." : "Lead not found."}</p>
        <button onClick={() => navigate("/leads")} className="mt-4 text-sm underline">{ar ? "العودة للقائمة" : "Back to leads"}</button>
      </div>
    );
  }

  const job = jobs.find((j) => j.id === lead.jobId);
  const icp = icps.find((i) => i.version === lead.icpVersion);
  const c = lead.company;
  const crit = lead.icpFit.criteria;
  const met = crit.filter((x) => x.match === "yes");
  const gaps = crit.filter((x) => x.match !== "yes");
  const contactOk = hasContact(lead);
  const canDecide = lead.status === "READY_FOR_REVIEW" || lead.status === "SAVED";
  const busy = lead.status === "IN_RESEARCH";

  const decide = (d) => {
    if (d === "RESEARCH_MORE") { researchMore(lead.id); return; }
    if (reviewLead(lead.id, d, note)) navigate("/review");
  };
  const reveal = () => { if (revealPII(lead.id, piiReason)) { setShowPiiForm(false); setPiiReason(""); } };

  return (
    <>
      <PageHeader
        title={c.name}
        subtitle={c.description}
        actions={
          <>
            <button onClick={back} className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition">
              <ArrowLeft className="w-4 h-4" /> {ar ? "رجوع" : "Back"}
            </button>
            <StatusBadge status={lead.status} size="base" />
          </>
        }
      />

      <div className="grid lg:grid-cols-[1fr_320px] gap-6 px-4 lg:px-8 py-6 max-w-[1400px]">
        <div className="space-y-5 min-w-0">
          {/* verdict: strengths vs gaps — the criteria table below holds the details */}
          <section className="card-surface p-5">
            <div className="flex items-center gap-5">
              <ScoreRing score={lead.icpFit.score} size={72} />
              <div className="min-w-0">
                <h2 className="text-sm font-semibold">{t("ld.whyLead")}</h2>
                <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                  {ar
                    ? `يطابق ${met.length} من ${crit.length} معايير في ${icp?.label || "ICP"} · الثقة ${lead.confidence} · تغطية الأدلة ${lead.evidenceCoverage}%`
                    : `Meets ${met.length} of ${crit.length} criteria in ${icp?.label || "ICP"} · confidence ${({ "عالية": "high", "متوسطة": "medium", "منخفضة": "low" })[lead.confidence] || lead.confidence} · evidence ${lead.evidenceCoverage}%`}
                </p>
              </div>
            </div>
            <div className="grid sm:grid-cols-2 gap-4 mt-4 pt-4 border-t border-border text-sm">
              <div>
                <div className="text-[11px] font-medium text-muted-foreground mb-1.5">{ar ? "نقاط القوة" : "Strengths"}</div>
                {met.length ? met.map((x) => <div key={x.name} className="flex items-center gap-2 py-0.5"><Check className="w-3.5 h-3.5 text-[hsl(var(--success))]" />{tr(x.name, lang)}: <b className="font-medium">{tr(x.value, lang)}</b></div>) : <span className="text-muted-foreground">—</span>}
              </div>
              <div>
                <div className="text-[11px] font-medium text-muted-foreground mb-1.5">{ar ? "فجوات تحتاج انتباهك" : "Gaps to consider"}</div>
                {gaps.length ? gaps.map((x) => (
                  <div key={x.name} className="flex items-center gap-2 py-0.5">
                    {x.match === "no" ? <XCircle className="w-3.5 h-3.5 text-[hsl(var(--danger))]" /> : <Minus className="w-3.5 h-3.5 text-[hsl(var(--warning))]" />}
                    {tr(x.name, lang)}: <b className="font-medium">{tr(x.value, lang)}</b> <span className="text-[11px] text-muted-foreground">({ar ? "المطلوب" : "wanted"} {tr(x.expected, lang)})</span>
                  </div>
                )) : <span className="text-muted-foreground">{ar ? "لا فجوات." : "No gaps."}</span>}
              </div>
            </div>
          </section>

          {/* criteria table */}
          <section className="card-surface p-5">
            <h2 className="text-sm font-semibold mb-3">{t("ld.icpFit")}</h2>
            <div className="overflow-x-auto -mx-5 px-5">
              <table className="w-full text-sm min-w-[460px]">
                <thead><tr className="text-[11px] text-muted-foreground border-b border-border">
                  <th className="font-medium py-2 text-start">{ar ? "المعيار" : "Criterion"}</th>
                  <th className="font-medium py-2 text-start">{ar ? "القيمة الفعلية" : "Actual"}</th>
                  <th className="font-medium py-2 text-start">{ar ? "المطلوب" : "Wanted"}</th>
                  <th className="font-medium py-2 text-center">{ar ? "النتيجة" : "Result"}</th>
                </tr></thead>
                <tbody>
                  {crit.map((cr) => (
                    <tr key={cr.name} className="border-b border-border/50">
                      <td className="py-2.5 text-muted-foreground">{tr(cr.name, lang)}</td>
                      <td className="py-2.5 font-medium">{tr(cr.value, lang)}</td>
                      <td className="py-2.5 text-muted-foreground">{tr(cr.expected, lang)}</td>
                      <td className="py-2.5 text-center"><MatchGlyph match={cr.match} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {lead.conflicts.length > 0 && (
            <section className="card-surface p-5 border-s-2 border-s-[hsl(var(--warning))]">
              <h2 className="text-sm font-semibold mb-3 flex items-center gap-2"><AlertTriangle className="w-4 h-4 text-[hsl(var(--warning))]" /> {t("ld.conflicts")}</h2>
              {lead.conflicts.map((cf, i) => (
                <div key={i} className="mb-1">
                  <div className="text-sm font-medium mb-2">{cf.property}</div>
                  <div className="grid sm:grid-cols-2 gap-2">
                    {cf.sources.map((s, si) => (
                      <div key={si} className="rounded-lg border border-border p-3 bg-muted/30">
                        <div className="text-[11px] text-muted-foreground mb-1">{s.source}</div>
                        <div className="text-lg font-display font-semibold tnum">{s.value}</div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </section>
          )}

          <section className="card-surface p-5">
            <h2 className="text-sm font-semibold mb-3">{t("ld.facts")}</h2>
            <div className="overflow-x-auto -mx-5 px-5">
              <table className="w-full text-sm min-w-[640px]">
                <thead><tr className="text-[11px] text-muted-foreground border-b border-border">
                  {[ar ? "المعلومة" : "Property", ar ? "القيمة" : "Value", ar ? "الحالة" : "Status", ar ? "المصدر" : "Source", ar ? "الحداثة" : "Freshness"].map((h) => <th key={h} className="font-medium py-2 text-start">{h}</th>)}
                </tr></thead>
                <tbody>
                  {lead.facts.map((f, i) => (
                    <tr key={i} className="border-b border-border/50 hover:bg-muted/30 transition">
                      <td className="py-2.5 text-muted-foreground">{tr(f.property, lang)}</td>
                      <td className="py-2.5 font-medium">{tr(f.value, lang)}</td>
                      <td className="py-2.5"><StatusBadge status={f.status} /></td>
                      <td className="py-2.5 text-muted-foreground">{tr(f.source, lang)}</td>
                      <td className="py-2.5 text-muted-foreground text-xs">{tr(f.freshness, lang)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="card-surface p-5">
            <h2 className="text-sm font-semibold mb-3">{t("ld.evidence")}</h2>
            <div className="space-y-3">
              {lead.evidence.map((e, i) => (
                <div key={i} className="rounded-lg border border-border p-3">
                  <p className="text-sm font-medium mb-1.5">{e.claim}</p>
                  <div className="flex flex-wrap gap-1.5">{e.sources.map((s, si) => <Pill key={si}>{s}</Pill>)}</div>
                </div>
              ))}
            </div>
          </section>

          <section className="card-surface p-5">
            <h2 className="text-sm font-semibold mb-3 flex items-center gap-2"><Clock className="w-4 h-4 text-muted-foreground" /> {t("ld.timeline")}</h2>
            <ol className="relative ps-5 space-y-4">
              <span className="absolute top-1 bottom-1 start-1.5 w-px bg-border" />
              {lead.timeline.map((ev, i) => (
                <li key={i} className="relative">
                  <span className="absolute -start-[18px] top-1 w-2.5 h-2.5 rounded-full bg-foreground ring-4 ring-background" />
                  <div className="flex items-center gap-2"><span className="text-sm font-medium">{eventLabel(ev.event, lang)}</span><TimeAgo iso={ev.at} /></div>
                  {ev.detail && <p className="text-xs text-muted-foreground mt-0.5">{ev.detail}</p>}
                </li>
              ))}
            </ol>
          </section>
        </div>

        <div className="space-y-5 lg:sticky lg:top-6 lg:self-start">
          {/* decision first: it is the point of this page */}
          <section className="card-surface p-5">
            <h2 className="text-sm font-semibold mb-3">{t("ld.decision")}</h2>
            {canDecide || busy ? (
              <div className="space-y-2">
                <textarea dir="auto" value={note} onChange={(e) => setNote(e.target.value)} placeholder={t("review.decisionNote")} rows={2} aria-label={t("review.decisionNote")}
                  className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm focus-ring resize-none" />
                <div className="grid grid-cols-2 gap-2">
                  <button disabled={busy || !contactOk} onClick={() => decide("APPROVED")} className="rounded-lg bg-[hsl(var(--success))] text-white py-2 text-xs font-semibold hover:opacity-90 transition inline-flex items-center justify-center gap-1.5 disabled:opacity-40 disabled:cursor-not-allowed"><CheckCircle2 className="w-3.5 h-3.5" /> {t("review.approve")}</button>
                  <button disabled={busy} onClick={() => decide("REJECTED")} className="rounded-lg bg-[hsl(var(--danger))] text-white py-2 text-xs font-semibold hover:opacity-90 transition inline-flex items-center justify-center gap-1.5 disabled:opacity-40"><XCircle className="w-3.5 h-3.5" /> {t("review.reject")}</button>
                  <button disabled={busy} onClick={() => decide("RESEARCH_MORE")} className="rounded-lg border border-border py-2 text-xs font-semibold hover:bg-muted transition inline-flex items-center justify-center gap-1.5 disabled:opacity-40"><FileSearch className="w-3.5 h-3.5" /> {t("review.researchMore")}</button>
                  {lead.status !== "SAVED" && <button disabled={busy} onClick={() => decide("SAVED")} className="rounded-lg border border-border py-2 text-xs font-semibold hover:bg-muted transition inline-flex items-center justify-center gap-1.5 disabled:opacity-40"><Clock className="w-3.5 h-3.5" /> {t("review.saveLater")}</button>}
                </div>
                {!contactOk && <p className="text-[11px] text-muted-foreground leading-relaxed">{canFindContacts ? (ar ? "الاعتماد يحتاج جهة اتصال. اضغط «ابحث أكثر» للعثور على صانع قرار." : "Approval needs a contact. Use Research more to find a decision maker.") : (ar ? "الاعتماد يحتاج جهة اتصال. اربط ZoomInfo من «بيانات الاعتماد» ثم اضغط «ابحث أكثر»." : "Approval needs a contact. Connect ZoomInfo under Credentials, then use Research more.")}</p>}
                {busy && <p className="text-[11px] text-muted-foreground">{ar ? "جارٍ البحث عن المعلومات الناقصة…" : "Looking for the missing information…"}</p>}
                <p className="text-[10px] text-muted-foreground leading-relaxed pt-1">{t("review.noSend")}</p>
              </div>
            ) : (
              <div className="text-sm space-y-2">
                <StatusBadge status={lead.status} size="base" />
                {lead.reviewAt && <div className="text-xs text-muted-foreground"><TimeAgo iso={lead.reviewAt} /></div>}
                {lead.reviewNote && <p className="text-xs text-muted-foreground">{lead.reviewNote}</p>}
              </div>
            )}
          </section>

          <section className="card-surface p-5">
            <h2 className="text-sm font-semibold mb-3">{t("ld.contact")}</h2>
            {lead.contact.piiAccessed ? (
              <dl className="space-y-2 text-sm">
                <Row label={ar ? "الاسم" : "Name"} value={lead.contact.name} />
                <Row label={ar ? "المسمى" : "Title"} value={lead.contact.title} />
                <Row label={ar ? "البريد" : "Email"} value={lead.contact.email} mono />
                <Row label={ar ? "الهاتف" : "Phone"} value={lead.contact.phone} mono />
                <Row label="LinkedIn" value={lead.contact.linkedin} mono />
                <div className="text-[10px] text-muted-foreground pt-2 border-t border-border">{ar ? "سبب الكشف" : "Reason"}: {lead.contact.revealReason} · <TimeAgo iso={lead.contact.revealAt} /></div>
              </dl>
            ) : !contactOk ? (
              <div className="text-sm text-muted-foreground py-1">{canFindContacts ? (ar ? "لم يُحدَّد صانع قرار بعد. استخدم «ابحث أكثر»." : "No decision maker yet. Use Research more.") : (ar ? "لم يُحدَّد صانع قرار — ZoomInfo غير مربوط." : "No decision maker — ZoomInfo is not connected.")}</div>
            ) : (
              <div>
                <p className="text-xs text-muted-foreground mb-3 leading-relaxed">{ar ? "بيانات الاتصال حساسة: يتطلب كشفها سببًا ويُسجَّل في سجل التدقيق." : "Contact data is sensitive: revealing it needs a reason and is audit-logged."}</p>
                {showPiiForm ? (
                  <div className="space-y-2">
                    <input dir="auto" autoFocus value={piiReason} onChange={(e) => setPiiReason(e.target.value)} onKeyDown={(e) => e.key === "Enter" && reveal()} placeholder={t("ld.piiReason")} aria-label={t("ld.piiReason")} className="w-full h-9 px-3 rounded-lg border border-input bg-background text-sm focus-ring" />
                    <div className="flex gap-2">
                      <button disabled={!piiReason.trim()} onClick={reveal} className="flex-1 rounded-lg bg-primary text-primary-foreground py-2 text-sm font-medium hover:opacity-90 disabled:opacity-40">{ar ? "كشف" : "Reveal"}</button>
                      <button onClick={() => { setShowPiiForm(false); setPiiReason(""); }} className="rounded-lg border border-border px-3 text-sm">{t("common.cancel")}</button>
                    </div>
                  </div>
                ) : (
                  <button onClick={() => setShowPiiForm(true)} className="w-full rounded-lg border border-border py-2 text-sm font-medium hover:bg-muted transition inline-flex items-center justify-center gap-2"><Eye className="w-4 h-4" /> {t("ld.revealPii")}</button>
                )}
              </div>
            )}
          </section>

          <section className="card-surface p-5">
            <h2 className="text-sm font-semibold mb-3">{t("ld.summary")}</h2>
            <dl className="space-y-2.5 text-sm">
              <Row label={ar ? "المجال" : "Domain"} value={c.domain} />
              <Row label={ar ? "الموقع" : "Location"} value={tr(c.location, lang)} />
              <Row label={ar ? "القطاع" : "Industry"} value={tr(c.industry, lang)} />
              <Row label={ar ? "الحجم" : "Size"} value={`${fmtNum(c.size, lang)} ${ar ? "موظف" : "employees"}`} />
              <Row label={ar ? "تأسست" : "Founded"} value={c.founded} />
              <Row label={ar ? "النموذج" : "Model"} value={c.businessModel} />
              <Row label={ar ? "الموقع الإلكتروني" : "Website"} value={<a href={c.website} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 underline underline-offset-2">{c.domain} <ExternalLink className="w-3 h-3" /></a>} />
            </dl>
            {job && <div className="mt-3 pt-3 border-t border-border text-[11px] text-muted-foreground">{ar ? "وظيفة البحث" : "Research job"}: <button onClick={() => navigate(`/jobs/${job.id}`)} className="underline underline-offset-2 text-foreground">{job.id}</button> · {icp?.label}</div>}
          </section>
        </div>
      </div>
    </>
  );
}

function Row({ label, value, mono }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-muted-foreground text-xs shrink-0">{label}</dt>
      <dd className={cn("font-medium text-end text-sm", mono && "font-mono text-xs")} dir={mono ? "ltr" : undefined}>{value}</dd>
    </div>
  );
}
