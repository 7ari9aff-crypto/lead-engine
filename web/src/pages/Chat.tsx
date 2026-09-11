import { useState, useRef, useEffect, KeyboardEvent } from "react";
import {
  Bot, User, Send, Wrench, CheckCircle2, XCircle, Loader2, Square,
  Plus, Trash2, Globe2, Mail, ListChecks, Activity, ChevronDown,
  Check, Copy, Plug, Cpu, MessageSquare, Sparkles, ShieldAlert,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { cn } from "@/lib/utils";
import { create } from "zustand";
import { persist } from "zustand/middleware";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { toast } from "sonner";
import { apiPost, apiGet } from "@/lib/api";
import { useLiveData } from "@/hooks/useLiveData";
import { Link } from "wouter";

// ===== Types =====
type Role = "user" | "assistant" | "system";

type ToolCall = {
  name: string;
  args: Record<string, any>;
  ok: boolean;
  summary: string;
  result?: any;
};

type Msg = {
  id: string;
  role: Role;
  content: string;
  ts: number;
  tools?: ToolCall[];
  pending?: boolean;
  error?: string;
  provider?: string | null;
};

type Session = {
  id: string;
  title: string;
  messages: Msg[];
  createdAt: number;
  updatedAt: number;
};

interface ChatState {
  sessions: Session[];
  currentId: string;
  addMsg: (s: string, m: Msg) => void;
  updateMsg: (s: string, id: string, patch: Partial<Msg>) => void;
  setCurrent: (id: string) => void;
  newSession: () => string;
  deleteSession: (id: string) => void;
  renameSession: (id: string, title: string) => void;
  clearAll: () => void;
}

const newId = () => Math.random().toString(36).slice(2, 10);
const now = () => Date.now();

const WELCOME =
  "أهلاً 👋 أنا مساعد محرك الـLeads.\n\nأقدر:\n- أشغّل خط توليد leads في أي مدينة سعودية\n- أفحص أي إيميل بخمس حالات مع كشف catch-all\n- أعرض حالة النظام والمهام والنتائج\n\nجرّب تطلب: «اعمل ليد جينيراشن في الرياض»";

const useChat = create<ChatState>()(
  persist(
    (set) => ({
      sessions: [
        {
          id: newId(),
          title: "محادثة جديدة",
          messages: [
            { id: newId(), role: "assistant", ts: now(), content: WELCOME },
          ],
          createdAt: now(),
          updatedAt: now(),
        },
      ],
      currentId: "",
      addMsg: (sid, m) =>
        set((s) => ({
          sessions: s.sessions.map((x) =>
            x.id === sid ? { ...x, messages: [...x.messages, m], updatedAt: now() } : x
          ),
        })),
      updateMsg: (sid, id, patch) =>
        set((s) => ({
          sessions: s.sessions.map((x) =>
            x.id === sid
              ? {
                  ...x,
                  messages: x.messages.map((m) => (m.id === id ? { ...m, ...patch } : m)),
                  updatedAt: now(),
                }
              : x
          ),
        })),
      setCurrent: (id) => set({ currentId: id }),
      newSession: () => {
        const id = newId();
        set((s) => ({
          currentId: id,
          sessions: [
            {
              id,
              title: "محادثة جديدة",
              messages: [
                { id: newId(), role: "assistant", ts: now(), content: WELCOME },
              ],
              createdAt: now(),
              updatedAt: now(),
            },
            ...s.sessions,
          ],
        }));
        return id;
      },
      deleteSession: (id) =>
        set((s) => {
          const remaining = s.sessions.filter((x) => x.id !== id);
          return { sessions: remaining, currentId: remaining[0]?.id ?? "" };
        }),
      renameSession: (id, title) =>
        set((s) => ({
          sessions: s.sessions.map((x) => (x.id === id ? { ...x, title } : x)),
        })),
      clearAll: () => set({ sessions: [], currentId: "" }),
    }),
    { name: "lead-engine-chat" }
  )
);

// ===== Composer preferences (agent + model + integrations) =====
interface ComposerState {
  agent: string | null;                // agent slug (null = default = lead-generation)
  provider: string | null;             // null = auto (router priority)
  enabledTools: string[] | null;       // null = all tools
  setAgent: (a: string | null) => void;
  setProvider: (p: string | null) => void;
  setEnabledTools: (t: string[] | null) => void;
}
const useComposer = create<ComposerState>()(
  persist(
    (set) => ({
      agent: null,
      provider: null,
      enabledTools: null,
      setAgent: (a) => set({ agent: a }),
      setProvider: (p) => set({ provider: p }),
      setEnabledTools: (t) => set({ enabledTools: t }),
    }),
    { name: "lead-engine-composer" }
  )
);

// ===== Model catalog =====
const MODELS = [
  { id: null, name: "تلقائي", desc: "الروتر يختار الأنسب حسب التوفر", short: "Auto" },
  { id: "gemini", name: "Gemini Flash", desc: "يدعم الأدوات — الأسرع للتشغيل الحقيقي", short: "Gemini" },
  { id: "groq", name: "Llama 3.3 70B · Groq", desc: "استجابة فورية — نص فقط بدون أدوات", short: "Groq" },
  { id: "openrouter", name: "Llama 3.3 70B · OpenRouter", desc: "المسار المجاني — نص فقط", short: "OpenRouter" },
  { id: "ollama", name: "Llama محلي · Ollama", desc: "على جهازك — بدون تكلفة، جودة أقل", short: "Ollama" },
];

// ===== Tool catalog (integrations picker) =====
const TOOLS = [
  { id: "run_lead_generation", name: "تشغيل التوليد", desc: "خط كامل — يحتاج موافقة", risky: true },
  { id: "list_leads", name: "عرض النتائج", desc: "قراءة الـleads المخزنة", risky: false },
  { id: "get_job_status", name: "حالة المهام", desc: "متابعة التشغيلات", risky: false },
  { id: "verify_email", name: "فحص إيميل", desc: "خمس حالات مع catch-all", risky: false },
  { id: "system_status", name: "حالة النظام", desc: "المزودون والاستهلاك", risky: false },
];

const QUICK_PROMPTS = [
  { icon: Globe2, title: "توليد leads في الرياض", prompt: "اعمل ليد جينيراشن في الرياض — عيادات أسنان" },
  { icon: ListChecks, title: "عرض آخر النتائج", prompt: "اعرض آخر 10 leads مقبولة من قاعدة البيانات" },
  { icon: Mail, title: "فحص إيميل", prompt: "افحص الإيميل: info@clinic.sa" },
  { icon: Activity, title: "حالة النظام", prompt: "إيش حالة النظام والمزوّدين الحين؟" },
];

// ===== Page =====
export function ChatPage() {
  const { sessions, currentId, addMsg, updateMsg, setCurrent, newSession, deleteSession, clearAll } = useChat();
  const { agent, setAgent, provider, setProvider, enabledTools, setEnabledTools } = useComposer();
  const session = sessions.find((s) => s.id === currentId) || sessions[0];

  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [modelOpen, setModelOpen] = useState(false);
  const [toolsOpen, setToolsOpen] = useState(false);
  const [agentOpen, setAgentOpen] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const { data: status } = useLiveData(() => apiGet.status(), 15000);
  const { data: agentsData } = useLiveData(() => apiGet.agents(), 30000);
  const agents = (agentsData?.agents ?? []) as Array<{ slug: string; name: string; description?: string; current_version?: string | null }>;
  const activeAgent = agents.find((a) => a.slug === agent) || agents.find((a) => a.slug === "lead-generation") || null;
  const reasoningProviders = (status?.providers ?? []).filter((p) => p.task === "reasoning");
  const availability = (id: string) => {
    const row = reasoningProviders.find((p) => p.name === id);
    if (!row) return false;
    return row.is_local || row.has_key;
  };
  const allToolsOn = enabledTools === null;
  const activeToolsCount = allToolsOn ? TOOLS.length : (enabledTools?.length ?? 0);
  const currentModel = MODELS.find((m) => m.id === provider) ?? MODELS[0];

  useEffect(() => {
    if (!currentId && sessions[0]) setCurrent(sessions[0].id);
  }, [currentId, sessions, setCurrent]);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [session?.messages.length, session?.messages[session.messages.length - 1]?.content]);

  // close popovers on outside click
  useEffect(() => {
    function onDoc(e: MouseEvent) {
      const t = e.target as HTMLElement;
      if (!t.closest("[data-popover]")) {
        setModelOpen(false);
        setToolsOpen(false);
        setAgentOpen(false);
      }
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  function autoGrow() {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 200) + "px";
  }

  async function send(text: string) {
    if (!text.trim() || !session || busy) return;
    const userMsg: Msg = { id: newId(), role: "user", content: text.trim(), ts: now() };
    addMsg(session.id, userMsg);
    setInput("");
    requestAnimationFrame(autoGrow);
    setBusy(true);

    if (session.messages.length <= 1) {
      useChat.getState().renameSession(session.id, text.trim().slice(0, 40));
    }

    const pendingId = newId();
    addMsg(session.id, { id: pendingId, role: "assistant", content: "", ts: now(), pending: true });

    abortRef.current = new AbortController();
    try {
      const apiMsgs = [...session.messages, userMsg].map((m) => ({ role: m.role, content: m.content }));
      const data = await apiPost.chat(apiMsgs, {
        provider,
        tools: allToolsOn ? null : enabledTools,
        agent,
      });
      updateMsg(session.id, pendingId, {
        content: data.reply || "(رد فارغ)",
        tools: data.tools || [],
        pending: false,
        provider: data.provider || null,
      });
    } catch (e: any) {
      updateMsg(session.id, pendingId, {
        content: "",
        pending: false,
        error: e.message || "حدث خطأ",
      });
      toast.error("فشل الاتصال بالمساعد");
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }

  function stop() {
    abortRef.current?.abort();
  }

  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(input);
    }
  }

  function toggleTool(id: string) {
    const base = allToolsOn ? TOOLS.map((t) => t.id) : (enabledTools ?? []);
    const next = base.includes(id) ? base.filter((x) => x !== id) : [...base, id];
    setEnabledTools(next.length === TOOLS.length ? null : next);
  }

  if (!session) {
    return <div className="text-center text-[var(--fg-muted)] py-20 h-full">لا توجد محادثات</div>;
  }

  const empty = session.messages.length === 0;

  return (
    <div className="h-full grid grid-cols-1 lg:grid-cols-[270px_1fr]">
      {/* ===== Conversations ===== */}
      <aside className="hidden lg:flex flex-col border-e border-[var(--border)] bg-[var(--bg-elev)]/40 min-h-0">
        <div className="flex items-center justify-between px-4 h-12 border-b border-[var(--border-soft)] shrink-0">
          <span className="text-xs font-semibold text-[var(--fg-muted)] flex items-center gap-2">
            <MessageSquare className="h-3.5 w-3.5" />
            المحادثات
          </span>
          <Button size="icon-sm" variant="ghost" onClick={() => newSession()} title="محادثة جديدة">
            <Plus className="h-4 w-4" />
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-0.5 min-h-0">
          {sessions.map((s) => (
            <button
              key={s.id}
              onClick={() => setCurrent(s.id)}
              className={cn(
                "w-full text-right rounded-lg px-3 py-2 text-[13px] transition-colors group flex items-center gap-2",
                s.id === session.id
                  ? "bg-[var(--accent-soft)] text-[var(--accent-hover)] font-medium"
                  : "text-[var(--fg-muted)] hover:bg-[var(--bg-hover)]"
              )}
            >
              <span className="flex-1 truncate">{s.title || "بدون عنوان"}</span>
              {sessions.length > 1 && (
                <span
                  role="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    if (confirm("حذف المحادثة؟")) deleteSession(s.id);
                  }}
                  className="opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-[var(--danger)]/20 hover:text-[var(--danger)] rounded"
                >
                  <Trash2 className="h-3 w-3" />
                </span>
              )}
            </button>
          ))}
        </div>
        {sessions.length > 1 && (
          <div className="p-2 border-t border-[var(--border-soft)] shrink-0">
            <Button
              size="sm"
              variant="ghost"
              onClick={() => { if (confirm("حذف كل المحادثات؟")) clearAll(); }}
              className="w-full text-[var(--danger)]"
            >
              <Trash2 className="h-3.5 w-3.5" />
              مسح الكل
            </Button>
          </div>
        )}
      </aside>

      {/* ===== Chat column ===== */}
      <section className="flex flex-col min-h-0 min-w-0">
        {/* Slim header */}
        <div className="flex items-center gap-2.5 px-4 lg:px-6 h-12 border-b border-[var(--border-soft)] shrink-0">
          <div className="h-7 w-7 rounded-lg bg-[image:var(--gradient)] flex items-center justify-center shrink-0">
            <Sparkles className="h-3.5 w-3.5 text-white" />
          </div>
          <h1 className="text-[13px] font-semibold truncate">{session.title || "المساعد الذكي"}</h1>
          <Badge variant="accent" className="text-[10px] shrink-0">{currentModel.short}</Badge>
          <span className="ms-auto text-[11px] text-[var(--fg-soft)] tnum shrink-0">
            {session.messages.filter((m) => m.role === "user").length} طلب
          </span>
        </div>

        {/* Log — fills the space */}
        <div ref={logRef} className="flex-1 overflow-y-auto min-h-0">
          <div className={cn("mx-auto w-full px-4 lg:px-6", empty ? "max-w-2xl py-16" : "max-w-3xl py-6 space-y-5")}>
            {empty ? (
              <div className="animate-fade-in">
                <div className="text-center mb-8">
                  <div className="h-12 w-12 rounded-2xl bg-[image:var(--gradient)] flex items-center justify-center mx-auto mb-4 shadow-[var(--shadow-lg)]">
                    <Sparkles className="h-5 w-5 text-white" />
                  </div>
                  <h2 className="text-xl font-bold mb-1.5">كيف أساعدك اليوم؟</h2>
                  <p className="text-sm text-[var(--fg-muted)]">
                    اطلب تشغيل توليد، أو اسأل عن حالة النظام — الأدوات تنفّذ فعليًا بمفاتيحك.
                  </p>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                  {QUICK_PROMPTS.map((qp, i) => {
                    const Icon = qp.icon;
                    return (
                      <button
                        key={i}
                        onClick={() => send(qp.prompt)}
                        disabled={busy}
                        className="text-right rounded-xl p-3.5 bg-[var(--bg-elev)] border border-[var(--border)] hover:border-[var(--accent)] hover:shadow-[var(--shadow)] transition-all group"
                      >
                        <Icon className="h-4 w-4 mb-2 text-[var(--accent)]" />
                        <div className="font-medium text-[13px]">{qp.title}</div>
                        <div className="text-[11px] text-[var(--fg-muted)] mt-0.5 line-clamp-1">{qp.prompt}</div>
                      </button>
                    );
                  })}
                </div>
              </div>
            ) : (
              session.messages.map((m) => <MessageBubble key={m.id} msg={m} />)
            )}
          </div>
        </div>

        {/* ===== Composer ===== */}
        <div className="shrink-0 px-4 lg:px-6 pb-4 pt-1 bg-[var(--bg)]">
          <div className="mx-auto w-full max-w-3xl">
            <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-elev)] shadow-[var(--shadow)] focus-within:border-[var(--accent)] focus-within:ring-2 focus-within:ring-[var(--ring)] transition-all">
              <textarea
                ref={taRef}
                value={input}
                onChange={(e) => { setInput(e.target.value); autoGrow(); }}
                onKeyDown={onKey}
                rows={1}
                placeholder={busy ? "المساعد ينفّذ الطلب…" : "اطلب أي شيء — مثال: اعمل ليد جينيراشن في جدة"}
                disabled={busy}
                className="w-full resize-none bg-transparent px-4 pt-3.5 pb-2 text-sm focus:outline-none disabled:opacity-60 placeholder:text-[var(--fg-soft)]"
              />
              {/* Composer toolbar */}
              <div className="flex items-center gap-1.5 px-2.5 pb-2.5">
                {/* Agent picker */}
                <div className="relative" data-popover>
                  <button
                    onClick={() => { setAgentOpen(!agentOpen); setModelOpen(false); setToolsOpen(false); }}
                    className="flex items-center gap-1.5 h-8 px-2.5 rounded-lg text-xs font-medium text-[var(--fg-muted)] hover:bg-[var(--bg-hover)] hover:text-[var(--fg)] transition-colors"
                    title="اختر الوكيل اللي يتكلم معاك"
                  >
                    <Bot className="h-3.5 w-3.5 text-[var(--accent)]" />
                    <span className="max-w-[120px] truncate">
                      {activeAgent ? activeAgent.name : "وكيل افتراضي"}
                    </span>
                    <ChevronDown className={cn("h-3 w-3 transition-transform", agentOpen && "rotate-180")} />
                  </button>
                  {agentOpen && (
                    <div className="absolute bottom-full mb-2 start-0 w-80 rounded-xl border border-[var(--border)] bg-[var(--bg-elev)] shadow-[var(--shadow-lg)] z-50 overflow-hidden animate-scale-in">
                      <div className="px-3 pt-2.5 pb-1.5 flex items-center justify-between">
                        <span className="text-[10px] font-semibold text-[var(--fg-soft)] uppercase tracking-wider">
                          الوكيل
                        </span>
                        <Link href="/agents" className="text-[11px] text-[var(--accent)] hover:underline">
                          إدارة →
                        </Link>
                      </div>
                      {agents.length === 0 ? (
                        <div className="px-3 py-4 text-[12px] text-[var(--fg-muted)]">
                          لا يوجد وكلاء. أنشئ واحد من صفحة الوكلاء.
                        </div>
                      ) : (
                        agents.map((a) => {
                          const selected = a.slug === (agent ?? "lead-generation");
                          return (
                            <button
                              key={a.slug}
                              onClick={() => { setAgent(a.slug); setAgentOpen(false); }}
                              className={cn(
                                "w-full flex items-start gap-2.5 px-3 py-2.5 text-right transition-colors",
                                selected ? "bg-[var(--accent-soft)]" : "hover:bg-[var(--bg-hover)]"
                              )}
                            >
                              <Bot className={cn(
                                "mt-1 h-3.5 w-3.5 shrink-0",
                                selected ? "text-[var(--accent)]" : "text-[var(--fg-soft)]"
                              )} />
                              <span className="flex-1 min-w-0">
                                <span className="flex items-center gap-1.5 text-[13px] font-medium text-[var(--fg)]">
                                  {a.name}
                                  {selected && <Check className="h-3.5 w-3.5 text-[var(--accent)]" />}
                                </span>
                                <span className="block text-[11px] text-[var(--fg-muted)] mt-0.5 truncate">
                                  {a.description || `slug: ${a.slug}`}
                                </span>
                              </span>
                            </button>
                          );
                        })
                      )}
                    </div>
                  )}
                </div>

                {/* Model picker */}
                <div className="relative" data-popover>
                  <button
                    onClick={() => { setModelOpen(!modelOpen); setToolsOpen(false); }}
                    className="flex items-center gap-1.5 h-8 px-2.5 rounded-lg text-xs font-medium text-[var(--fg-muted)] hover:bg-[var(--bg-hover)] hover:text-[var(--fg)] transition-colors"
                  >
                    <Cpu className="h-3.5 w-3.5 text-[var(--accent)]" />
                    {currentModel.short}
                    <ChevronDown className={cn("h-3 w-3 transition-transform", modelOpen && "rotate-180")} />
                  </button>
                  {modelOpen && (
                    <div className="absolute bottom-full mb-2 start-0 w-72 rounded-xl border border-[var(--border)] bg-[var(--bg-elev)] shadow-[var(--shadow-lg)] z-50 overflow-hidden animate-scale-in">
                      <div className="px-3 pt-2.5 pb-1.5 text-[10px] font-semibold text-[var(--fg-soft)] uppercase tracking-wider">
                        الموديل
                      </div>
                      {MODELS.map((m) => {
                        const selected = m.id === provider;
                        const available = m.id === null || availability(m.id);
                        return (
                          <button
                            key={m.short}
                            onClick={() => { setProvider(m.id); setModelOpen(false); }}
                            className={cn(
                              "w-full flex items-start gap-2.5 px-3 py-2.5 text-right transition-colors",
                              selected ? "bg-[var(--accent-soft)]" : "hover:bg-[var(--bg-hover)]"
                            )}
                          >
                            <span className={cn(
                              "mt-1 h-1.5 w-1.5 rounded-full shrink-0",
                              available ? "bg-[var(--success)]" : "bg-[var(--danger)]"
                            )} title={available ? "متاح" : "المفتاح غير مضبوط"} />
                            <span className="flex-1 min-w-0">
                              <span className="flex items-center gap-1.5 text-[13px] font-medium text-[var(--fg)]">
                                {m.name}
                                {selected && <Check className="h-3.5 w-3.5 text-[var(--accent)]" />}
                              </span>
                              <span className="block text-[11px] text-[var(--fg-muted)] mt-0.5">{m.desc}</span>
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>

                {/* Integrations / tools picker */}
                <div className="relative" data-popover>
                  <button
                    onClick={() => { setToolsOpen(!toolsOpen); setModelOpen(false); }}
                    className="flex items-center gap-1.5 h-8 px-2.5 rounded-lg text-xs font-medium text-[var(--fg-muted)] hover:bg-[var(--bg-hover)] hover:text-[var(--fg)] transition-colors"
                  >
                    <Plug className="h-3.5 w-3.5 text-[var(--accent)]" />
                    الأدوات
                    <span className="tnum text-[10px] rounded-md bg-[var(--bg-soft)] border border-[var(--border-soft)] px-1.5 py-px text-[var(--fg-muted)]">
                      {activeToolsCount}/{TOOLS.length}
                    </span>
                  </button>
                  {toolsOpen && (
                    <div className="absolute bottom-full mb-2 start-0 w-80 rounded-xl border border-[var(--border)] bg-[var(--bg-elev)] shadow-[var(--shadow-lg)] z-50 overflow-hidden animate-scale-in">
                      <div className="px-3 pt-2.5 pb-1.5 flex items-center justify-between">
                        <span className="text-[10px] font-semibold text-[var(--fg-soft)] uppercase tracking-wider">
                          أدوات المساعد
                        </span>
                        <button
                          onClick={() => setEnabledTools(allToolsOn ? [] : null)}
                          className="text-[11px] text-[var(--accent)] hover:underline"
                        >
                          {allToolsOn ? "إلغاء الكل" : "تفعيل الكل"}
                        </button>
                      </div>
                      {TOOLS.map((t) => {
                        const on = allToolsOn || (enabledTools ?? []).includes(t.id);
                        return (
                          <button
                            key={t.id}
                            onClick={() => toggleTool(t.id)}
                            className="w-full flex items-center gap-2.5 px-3 py-2.5 text-right hover:bg-[var(--bg-hover)] transition-colors"
                          >
                            <span className={cn(
                              "h-4 w-4 rounded-md border flex items-center justify-center shrink-0 transition-colors",
                              on ? "bg-[var(--accent)] border-[var(--accent)]" : "border-[var(--border)]"
                            )}>
                              {on && <Check className="h-3 w-3 text-white" />}
                            </span>
                            <span className="flex-1 min-w-0">
                              <span className="flex items-center gap-1.5 text-[13px] font-medium text-[var(--fg)]">
                                {t.name}
                                {t.risky && <ShieldAlert className="h-3 w-3 text-[var(--warn)]" />}
                              </span>
                              <span className="block text-[11px] text-[var(--fg-muted)] mt-0.5">{t.desc}</span>
                            </span>
                          </button>
                        );
                      })}
                      <div className="border-t border-[var(--border-soft)] p-3">
                        <div className="flex items-center justify-between gap-2">
                          <div className="min-w-0">
                            <div className="text-[11px] font-medium text-[var(--fg)] flex items-center gap-1.5">
                              <Plug className="h-3 w-3 text-[var(--accent)]" />
                              خادم MCP الخاص بالنظام
                            </div>
                            <div className="text-[10px] text-[var(--fg-muted)] mt-0.5">
                              نفس الأدوات متاحة لأي عميل MCP خارجي
                            </div>
                          </div>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => {
                              const url = `${window.location.origin}/mcp`;
                              navigator.clipboard?.writeText(url);
                              toast.success("تم نسخ رابط MCP");
                            }}
                          >
                            <Copy className="h-3 w-3" />
                            نسخ الرابط
                          </Button>
                        </div>
                      </div>
                    </div>
                  )}
                </div>

                <span className="ms-auto" />
                {busy ? (
                  <Button variant="danger" size="icon-sm" onClick={stop} title="إيقاف">
                    <Square className="h-3.5 w-3.5" />
                  </Button>
                ) : (
                  <Button
                    variant="primary"
                    size="icon-sm"
                    onClick={() => send(input)}
                    disabled={!input.trim()}
                    title="إرسال"
                  >
                    <Send className="h-3.5 w-3.5" />
                  </Button>
                )}
              </div>
            </div>
            <p className="text-[10px] text-[var(--fg-soft)] text-center mt-2">
              Enter للإرسال · Shift+Enter سطر جديد — التشغيل الحي يحتاج موافقة من لوحة الوكلاء
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}

// ===== Message =====
function MessageBubble({ msg }: { msg: Msg }) {
  const isUser = msg.role === "user";
  return (
    <div className="flex gap-3 animate-slide-up">
      <div
        className={cn(
          "h-7 w-7 rounded-lg flex items-center justify-center shrink-0 mt-0.5",
          isUser
            ? "bg-[var(--bg-soft)] border border-[var(--border)]"
            : "bg-[image:var(--gradient)]"
        )}
      >
        {isUser ? <User className="h-3.5 w-3.5" /> : <Bot className="h-3.5 w-3.5 text-white" />}
      </div>

      <div className="flex-1 min-w-0 space-y-1.5">
        <div className="text-[10px] text-[var(--fg-soft)] flex items-center gap-2">
          <span className="font-semibold text-[var(--fg-muted)]">{isUser ? "أنت" : "المساعد"}</span>
          {msg.provider && <span className="px-1.5 rounded bg-[var(--bg-soft)] border border-[var(--border-soft)]" dir="ltr">{msg.provider}</span>}
          {new Date(msg.ts).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })}
        </div>

        {msg.pending ? (
          <div className="inline-flex items-center gap-2 rounded-xl bg-[var(--bg-soft)] px-3.5 py-2.5 border border-[var(--border)]">
            <Loader2 className="h-3.5 w-3.5 animate-spin text-[var(--accent)]" />
            <span className="text-[13px] text-[var(--fg-muted)]">ينفّذ ويجيب النتائج…</span>
          </div>
        ) : msg.error ? (
          <div className="rounded-xl border border-[var(--danger)]/40 bg-[var(--danger)]/10 px-3.5 py-2.5">
            <div className="flex items-center gap-2 text-[var(--danger)] text-[13px] font-medium">
              <XCircle className="h-3.5 w-3.5" /> فشل الطلب
            </div>
            <div className="text-xs text-[var(--fg-muted)] mt-1">{msg.error}</div>
          </div>
        ) : (
          <div
            className={cn(
              "rounded-xl px-3.5 py-2.5 inline-block max-w-full",
              isUser
                ? "bg-[var(--accent)] text-white"
                : "bg-[var(--bg-elev)] border border-[var(--border)]"
            )}
          >
            {isUser ? (
              <div className="text-[13px] whitespace-pre-wrap break-words">{msg.content}</div>
            ) : (
              <div className="md-body text-[13px] text-[var(--fg)]">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
              </div>
            )}
          </div>
        )}

        {msg.tools && msg.tools.length > 0 && (
          <details className="rounded-xl border border-[var(--border)] bg-[var(--bg-soft)] overflow-hidden text-xs max-w-2xl">
            <summary className="cursor-pointer px-3 py-2 font-medium flex items-center gap-2 hover:bg-[var(--bg-hover)]">
              <Wrench className="h-3.5 w-3.5 text-[var(--accent)]" />
              {msg.tools.length} أداة نُفّذت فعليًا
            </summary>
            <div className="p-2.5 space-y-1.5 border-t border-[var(--border)]">
              {msg.tools.map((t, i) => (
                <div key={i} className="rounded-lg p-2 bg-[var(--bg-elev)] border border-[var(--border-soft)]">
                  <div className="flex items-center gap-2 font-medium">
                    {t.ok ? (
                      <CheckCircle2 className="h-3.5 w-3.5 text-[var(--success)]" />
                    ) : (
                      <XCircle className="h-3.5 w-3.5 text-[var(--danger)]" />
                    )}
                    <span dir="ltr" className="font-mono">{t.name}</span>
                  </div>
                  {Object.keys(t.args || {}).length > 0 && (
                    <pre className="mt-1.5 text-[11px] text-[var(--fg-muted)] whitespace-pre-wrap">{JSON.stringify(t.args, null, 2)}</pre>
                  )}
                  {t.summary && (
                    <pre className="mt-1.5 text-[11px] text-[var(--fg-muted)] whitespace-pre-wrap max-h-32 overflow-auto">{t.summary}</pre>
                  )}
                </div>
              ))}
            </div>
          </details>
        )}
      </div>
    </div>
  );
}
