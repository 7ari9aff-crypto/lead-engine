import React, { useState, useRef, useEffect, useLayoutEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { useLeadEngine, isLiveStatus } from "@/lib/leadEngine/store";
import { chatStatusLabel } from "@/lib/leadEngine/i18n";
import { StatusBadge, TimeAgo, ProgressBar, ScoreRing, ConfirmButton } from "@/components/leadEngine/primitives";
import {
  Bot, ArrowUp, Square, Copy, Check, SquarePen, PanelRightClose, PanelRightOpen, ChevronDown,
  Loader2, CircleCheck, Circle, ArrowUpRight, Search, Microscope, ShieldCheck, Filter, Eye,
} from "lucide-react";

const STAGES = [
  { key: "discovered", ar: "اكتشاف الشركات", en: "Discovering companies", status: "DISCOVERING" },
  { key: "deduplicated", ar: "إزالة التكرار", en: "Removing duplicates", status: "DISCOVERING" },
  { key: "researched", ar: "البحث في كل شركة", en: "Researching each company", status: "RESEARCHING" },
  { key: "verified", ar: "التحقق من المعلومات", en: "Verifying the facts", status: "VERIFYING" },
  { key: "qualified", ar: "التأهيل مقابل ICP", en: "Scoring against your ICP", status: "QUALIFYING" },
  { key: "readyForReview", ar: "تجهيز النتائج للمراجعة", en: "Preparing results for review", status: "READY_FOR_REVIEW" },
];
const ACTIONS = [
  { icon: Search, ar: "بحث", en: "Search", on: "DISCOVERING" },
  { icon: Microscope, ar: "تحقيق", en: "Research", on: "RESEARCHING" },
  { icon: ShieldCheck, ar: "تحقق", en: "Verify", on: "VERIFYING" },
  { icon: Filter, ar: "تأهيل", en: "Qualify", on: "QUALIFYING" },
  { icon: Eye, ar: "عرض", en: "Present", on: "READY_FOR_REVIEW" },
];
const SUGGESTIONS = {
  ar: ["شركات SaaS في الرياض بين 20 و200 موظف تحتاج أتمتة مبيعات", "شركات تقنية مالية في الرياض تستخدم Salesforce", "شركات برمجيات مؤسسية تبحث عن CRM جديد"],
  en: ["B2B SaaS companies in Riyadh with 20–200 employees that need sales automation", "Fintech companies in Riyadh using Salesforce", "Enterprise software firms looking for a new CRM"],
};

export default function Chat() {
  const { lang, chat, jobs, leads, currentUser, activeJobId, submitObjective, answerClarification, cancelJob } = useLeadEngine();
  const navigate = useNavigate();
  const ar = lang === "ar";
  const [input, setInput] = useState("");
  const [hint, setHint] = useState("");
  const [panel, setPanel] = useState(() => (typeof window === "undefined" ? true : window.innerWidth >= 1280));
  const [atBottom, setAtBottom] = useState(true);
  const scroller = useRef(null);
  const box = useRef(null);

  const job = jobs.find((j) => j.id === activeJobId) || jobs[0];
  const waiting = job?.status === "WAITING_FOR_USER" && job?.waitingQuestion;
  const live = isLiveStatus(job?.status);
  const jobLeads = leads.filter((l) => l.jobId === job?.id);
  const pending = jobLeads.filter((l) => l.status === "READY_FOR_REVIEW").length;
  const showSuggestions = !live && !waiting;

  // follow new content only while the user is already at the bottom
  const toBottom = useCallback((smooth = true) => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: smooth ? "smooth" : "auto" });
  }, []);
  const onScroll = () => {
    const el = scroller.current;
    setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 120);
  };
  useLayoutEffect(() => { toBottom(false); }, []);  
  useEffect(() => { if (atBottom) toBottom(); }, [chat.length, waiting, job?.status, job?.stages?.readyForReview]);  

  // textarea grows with its content, up to a limit
  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`;
  }, [input]);

  const send = (text = input) => {
    const v = text.trim();
    if (!v) return;
    setHint("");
    if (waiting) {
      // a typed answer works too — as long as it contains the number the agent asked for
      if (/\d+/.test(v)) { answerClarification(job.id, v); setInput(""); }
      else setHint(ar ? "اكتب رقمًا (مثل 5) أو اختر من الخيارات." : "Type a number (e.g. 5) or pick an option.");
      return;
    }
    submitObjective(v);
    setInput("");
    setAtBottom(true);
  };

  // 1 / 2 / 3 answers the pending question when the composer is empty
  useEffect(() => {
    if (!waiting) return;
    const onKey = (e) => {
      if (input.trim()) return; // typing something else — never hijack the keys
      const i = parseInt(e.key, 10) - 1;
      if (i >= 0 && i < job.waitingQuestion.options.length) {
        e.preventDefault(); // the digit is a shortcut, not text
        answerClarification(job.id, job.waitingQuestion.options[i]);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [waiting, input, job, answerClarification]);

  const newResearch = () => { setInput(""); setHint(""); box.current?.focus(); toBottom(); };

  return (
    <div className="h-full flex min-h-0 bg-background">
      <div className="flex-1 min-w-0 flex flex-col">
        {/* slim header — the page is the conversation */}
        <div className="h-12 shrink-0 px-4 lg:px-6 flex items-center justify-between gap-3 border-b border-border">
          <div className="flex items-center gap-2.5 min-w-0">
            <h1 className="text-sm font-semibold">{ar ? "شات البحث" : "Research Chat"}</h1>
            {job && <StatusBadge status={job.status} pulse={live} />}
          </div>
          <div className="flex items-center gap-1.5">
            <button onClick={newResearch} className="h-8 px-3 rounded-lg border border-border text-xs font-medium hover:bg-muted transition inline-flex items-center gap-1.5">
              <SquarePen className="w-3.5 h-3.5" /> {ar ? "بحث جديد" : "New research"}
            </button>
            <button onClick={() => setPanel((p) => !p)} aria-label={ar ? "تفاصيل البحث" : "Run details"} aria-pressed={panel}
              className="hidden lg:grid h-8 w-8 place-items-center rounded-lg border border-border hover:bg-muted transition">
              {panel ? <PanelRightClose className="w-4 h-4" /> : <PanelRightOpen className="w-4 h-4" />}
            </button>
          </div>
        </div>

        <div className="relative flex-1 min-h-0">
          <div ref={scroller} onScroll={onScroll} className="absolute inset-0 overflow-y-auto scrollbar-thin" aria-live="polite">
            <div className="mx-auto w-full max-w-4xl px-4 lg:px-8 py-8 space-y-7">
              {chat.map((m, i) => <Message key={m.id} m={m} lang={lang} user={currentUser} first={i === 0 || chat[i - 1].role !== m.role} />)}

              {waiting && <Question job={job} ar={ar} onAnswer={(a) => answerClarification(job.id, a)} />}

              {live && <LiveRun job={job} ar={ar} onStop={() => cancelJob(job.id)} />}

              {job?.status === "CANCELLED" && job._live !== undefined && (
                <Note ar={ar} text={ar ? "تم إيقاف هذا البحث." : "This research was stopped."} />
              )}

              {(job?.status === "READY_FOR_REVIEW" || job?.status === "COMPLETED") && jobLeads.length > 0 && (
                <Results leads={jobLeads} pending={pending} ar={ar} navigate={navigate} />
              )}
            </div>
          </div>

          {!atBottom && (
            <button onClick={() => toBottom()} aria-label={ar ? "إلى آخر الرسائل" : "Scroll to latest"}
              className="absolute bottom-3 left-1/2 -translate-x-1/2 h-9 w-9 rounded-full border border-border bg-card shadow-md grid place-items-center hover:bg-muted transition">
              <ChevronDown className="w-4 h-4" />
            </button>
          )}
        </div>

        {/* composer */}
        <div className="shrink-0 px-4 lg:px-8 pb-4 pt-2">
          <div className="mx-auto w-full max-w-4xl">
            {showSuggestions && (
              <div className="flex flex-wrap gap-2 mb-3">
                {SUGGESTIONS[lang].map((s) => (
                  <button key={s} onClick={() => { setInput(s); box.current?.focus(); }}
                    className="text-start text-xs px-3 py-2 rounded-xl border border-border bg-card hover:bg-muted hover:border-foreground/30 transition max-w-full" dir="auto">{s}</button>
                ))}
              </div>
            )}
            <div className="rounded-2xl border border-input bg-card shadow-sm focus-within:border-foreground/50 focus-within:shadow-md transition">
              <textarea
                ref={box} value={input} rows={2} dir="auto"
                onChange={(e) => { setInput(e.target.value); setHint(""); }}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(); } }}
                aria-label={ar ? "رسالتك" : "Your message"}
                placeholder={waiting ? (ar ? "اكتب رقمًا أو اختر من الخيارات أعلاه…" : "Type a number or pick an option above…") : (ar ? "صف العميل المثالي الذي تريد الوصول إليه…" : "Describe the ideal customer you want to reach…")}
                className="w-full resize-none bg-transparent px-4 pt-3.5 pb-1 text-[15px] leading-7 focus:outline-none placeholder:text-muted-foreground"
              />
              <div className="flex items-center justify-between gap-3 px-3 pb-2.5">
                <span className="text-[11px] text-muted-foreground px-1">
                  {hint || (ar ? "Enter للإرسال · Shift+Enter لسطر جديد" : "Enter to send · Shift+Enter for a new line")}
                </span>
                {live ? (
                  <ConfirmButton onConfirm={() => cancelJob(job.id)} confirmLabel={ar ? "تأكيد الإيقاف" : "Confirm stop"}
                    className="h-9 px-3.5 rounded-xl border border-border text-xs font-medium hover:bg-muted transition inline-flex items-center gap-1.5"
                    confirmClassName="h-9 px-3.5 rounded-xl bg-[hsl(var(--danger))] text-white text-xs font-medium inline-flex items-center gap-1.5">
                    <Square className="w-3.5 h-3.5 fill-current" /> {ar ? "إيقاف البحث" : "Stop"}
                  </ConfirmButton>
                ) : (
                  <button onClick={() => send()} disabled={!input.trim()} aria-label={ar ? "إرسال" : "Send"}
                    className="h-9 w-9 rounded-xl bg-primary text-primary-foreground grid place-items-center disabled:opacity-30 hover:opacity-90 transition">
                    <ArrowUp className="w-[18px] h-[18px]" strokeWidth={2.5} />
                  </button>
                )}
              </div>
            </div>
            <p className="text-center text-[11px] text-muted-foreground mt-2">
              {ar ? "الوكيل يبحث ويتحقق فقط — لا يراسل أي جهة، والقرار النهائي لك." : "The agent researches and verifies only — it never contacts anyone, and the final call is yours."}
            </p>
          </div>
        </div>
      </div>

      {panel && (
        <aside className="hidden lg:block w-[340px] shrink-0 border-s border-border bg-card overflow-y-auto scrollbar-thin">
          <RunPanel job={job} ar={ar} live={live} />
        </aside>
      )}
    </div>
  );
}

/* ---------- messages ---------- */
function Message({ m, lang, user, first }) {
  const isUser = m.role === "user";
  const [copied, setCopied] = useState(false);
  const initials = user.name.split(" ").map((n) => n[0]).slice(0, 2).join("");
  const copy = async () => { try { await navigator.clipboard.writeText(m.text); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* clipboard blocked */ } };
  return (
    <div className={cn("group flex gap-3.5 animate-slide-up", isUser && "flex-row-reverse", !first && "-mt-4")}>
      <div className={cn("w-8 h-8 rounded-lg grid place-items-center shrink-0 text-[11px] font-semibold", first ? "" : "invisible", isUser ? "bg-secondary border border-border" : "bg-primary text-primary-foreground dark:bg-accent dark:text-foreground")}>
        {isUser ? initials : <Bot className="w-4 h-4" />}
      </div>
      <div className={cn("min-w-0 max-w-[85%]", isUser && "flex flex-col items-end")}>
        {!isUser && first && m.status && <div className="text-[11px] text-muted-foreground mb-1">{chatStatusLabel(m.status, lang)}</div>}
        <div dir="auto" className={cn("whitespace-pre-wrap break-words text-[15px] leading-7 rounded-2xl px-4 py-2.5",
          isUser ? "bg-primary text-primary-foreground dark:bg-accent dark:text-foreground rounded-ee-md" : "bg-muted text-foreground rounded-es-md")}>{m.text}</div>
        <div className="flex items-center gap-2 mt-1 px-1 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition text-[10px] text-muted-foreground">
          <TimeAgo iso={m.at} />
          {!isUser && (
            <button onClick={copy} aria-label={lang === "ar" ? "نسخ" : "Copy"} className="inline-flex items-center gap-1 hover:text-foreground">
              {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}{copied ? (lang === "ar" ? "تم" : "Copied") : (lang === "ar" ? "نسخ" : "Copy")}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function Frame({ children, className }) {
  return (
    <div className="flex gap-3.5 animate-fade-in">
      <div className="w-8 h-8 rounded-lg bg-primary text-primary-foreground dark:bg-accent dark:text-foreground grid place-items-center shrink-0"><Bot className="w-4 h-4" /></div>
      <div className={cn("min-w-0 flex-1 max-w-[85%]", className)}>{children}</div>
    </div>
  );
}

function Question({ job, ar, onAnswer }) {
  const q = job.waitingQuestion;
  return (
    <Frame>
      <div className="rounded-2xl border border-[hsl(var(--warning)/0.4)] bg-[hsl(var(--warning-soft))] p-4">
        <div className="text-[15px] font-medium leading-7" dir="auto">{q.prompt}</div>
        <div className="flex flex-wrap gap-2 mt-3">
          {q.options.map((opt, i) => (
            <button key={opt} onClick={() => onAnswer(opt)} className="focus-ring inline-flex items-center gap-2 rounded-xl border border-border bg-card px-3.5 py-2 text-sm hover:border-foreground/50 hover:bg-muted transition">
              <kbd className="text-[10px] font-mono text-muted-foreground border border-border rounded px-1">{i + 1}</kbd>{opt}
            </button>
          ))}
        </div>
      </div>
    </Frame>
  );
}

function LiveRun({ job, ar, onStop }) {
  const current = STAGES.findLastIndex((s) => (job.stages?.[s.key] || 0) > 0);
  return (
    <Frame>
      <div className="rounded-2xl border border-border bg-card p-4">
        <div className="flex items-center justify-between gap-3 mb-3">
          <div className="flex items-center gap-2 text-sm font-semibold"><Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />{ar ? "جارٍ البحث…" : "Researching…"}</div>
          <ConfirmButton onConfirm={onStop} confirmLabel={ar ? "تأكيد الإيقاف" : "Confirm stop"}
            className="text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-1"
            confirmClassName="text-xs font-semibold text-[hsl(var(--danger-ink))]">
            <Square className="w-3 h-3 fill-current" /> {ar ? "إيقاف" : "Stop"}
          </ConfirmButton>
        </div>
        <ul className="space-y-2">
          {STAGES.map((s, i) => {
            const val = job.stages?.[s.key] || 0;
            const target = job.targets?.[s.key] || 0;
            const done = i < current || (target > 0 && val >= target);
            const active = !done && i === current;
            return (
              <li key={s.key} className={cn("flex items-center gap-2.5 text-sm", !done && !active && "text-muted-foreground")}>
                {done ? <CircleCheck className="w-4 h-4 text-[hsl(var(--success))] shrink-0" /> : active ? <Loader2 className="w-4 h-4 animate-spin shrink-0" /> : <Circle className="w-4 h-4 shrink-0 opacity-40" />}
                <span className={cn("flex-1", active && "font-medium text-foreground")}>{ar ? s.ar : s.en}</span>
                {(done || active) && <span className="font-display font-semibold tnum text-xs">{val}{target ? <span className="text-muted-foreground font-normal"> / {target}</span> : null}</span>}
              </li>
            );
          })}
        </ul>
      </div>
    </Frame>
  );
}

function Results({ leads, pending, ar, navigate }) {
  const top = [...leads].sort((a, b) => b.icpFit.score - a.icpFit.score);
  return (
    <Frame>
      <div className="rounded-2xl border border-[hsl(var(--success)/0.4)] bg-card overflow-hidden">
        <div className="px-4 py-3 flex items-center justify-between gap-3 border-b border-border bg-[hsl(var(--success-soft))]">
          <div>
            <div className="text-sm font-semibold flex items-center gap-2"><CircleCheck className="w-4 h-4 text-[hsl(var(--success))]" />{ar ? `اكتمل البحث — ${leads.length} نتائج` : `Research complete — ${leads.length} results`}</div>
            <div className="text-xs text-muted-foreground mt-0.5">{pending > 0 ? (ar ? `${pending} بانتظار قرارك` : `${pending} waiting for your decision`) : (ar ? "تمت مراجعة كل النتائج." : "All results reviewed.")}</div>
          </div>
          {pending > 0 && (
            <button onClick={() => navigate("/review")} className="focus-ring shrink-0 rounded-lg bg-primary text-primary-foreground px-3 py-1.5 text-xs font-medium hover:opacity-90 inline-flex items-center gap-1">
              {ar ? "افتح قائمة المراجعة" : "Open Review Queue"} <ArrowUpRight className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
        <ul className="divide-y divide-border">
          {top.map((l) => (
            <li key={l.id}>
              <button onClick={() => navigate(`/leads/${l.id}`)} className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-muted/50 transition text-start">
                <ScoreRing score={l.icpFit.score} size={38} />
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium truncate">{l.company.name}</div>
                  <div className="text-[11px] text-muted-foreground truncate">{l.company.industry} · {l.company.location}</div>
                </div>
                <StatusBadge status={l.status} />
              </button>
            </li>
          ))}
        </ul>
      </div>
    </Frame>
  );
}

function Note({ text }) {
  return <div className="text-center text-xs text-muted-foreground">{text}</div>;
}

/* ---------- side panel ---------- */
function RunPanel({ job, ar, live }) {
  if (!job) return null;
  const base = Math.max(job.stages?.discovered || 0, 1);
  const budgetPct = job.budget ? Math.round((job.budget.used / job.budget.limit) * 100) : 0;
  return (
    <div className="p-5 space-y-6">
      <div>
        <div className="text-[11px] font-medium text-muted-foreground mb-1.5">{ar ? "الهدف" : "Objective"}</div>
        <p className="text-sm leading-relaxed" dir="auto">{job.objective}</p>
        <div className="mt-2 flex items-center gap-2 text-[11px] text-muted-foreground font-mono">{job.id} · ICP v{job.icpVersion}</div>
      </div>

      <div>
        <h3 className="text-xs font-semibold mb-3">{ar ? "تقدّم البحث" : "Progress"}</h3>
        <div className="space-y-3">
          {STAGES.map((s, i) => {
            const val = job.stages?.[s.key] || 0;
            return (
              <div key={s.key} className={cn(!val && "opacity-45")}>
                <div className="flex justify-between text-xs mb-1"><span className="text-muted-foreground">{ar ? s.ar : s.en}</span><span className="font-display font-semibold tnum">{val}</span></div>
                <ProgressBar value={val} max={base} tone={i === 5 ? "success" : "primary"} />
              </div>
            );
          })}
        </div>
      </div>

      {job.budget && (
        <div>
          <div className="flex justify-between text-xs mb-1.5"><span className="font-semibold">{ar ? "الميزانية" : "Budget"}</span><span className="tnum text-muted-foreground">{job.budget.used.toLocaleString()} / {job.budget.limit.toLocaleString()}</span></div>
          <ProgressBar value={budgetPct} tone={budgetPct > 85 ? "danger" : "info"} />
        </div>
      )}

      <div>
        <h3 className="text-xs font-semibold mb-2.5">{ar ? "ما يفعله الوكيل الآن" : "What the agent is doing"}</h3>
        <div className="grid grid-cols-5 gap-1.5">
          {ACTIONS.map((a) => {
            const on = job.status === a.on;
            return (
              <div key={a.en} className={cn("rounded-lg border p-2 text-center transition", on ? "border-foreground/50 bg-accent" : "border-border bg-muted/40 opacity-60")}>
                <a.icon className="w-4 h-4 mx-auto mb-1" />
                <div className="text-[10px] font-medium">{ar ? a.ar : a.en}</div>
              </div>
            );
          })}
        </div>
        <p className="text-[10px] text-muted-foreground mt-2 leading-relaxed">{ar ? "لا يوجد إجراء «إرسال» — النظام لا يراسل أي جهة." : "There is no “send” action — the system never contacts anyone."}</p>
      </div>
    </div>
  );
}
