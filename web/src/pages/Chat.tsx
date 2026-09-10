import { useState, useRef, useEffect, KeyboardEvent } from "react";
import {
  Bot,
  User,
  Send,
  Sparkles,
  Wrench,
  CheckCircle2,
  XCircle,
  Loader2,
  Square,
  RotateCcw,
  Plus,
  Trash2,
  Globe2,
  Mail,
  ListChecks,
  Activity,
  Lightbulb,
} from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { cn, formatNumber } from "@/lib/utils";
import { create } from "zustand";
import { persist } from "zustand/middleware";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { toast } from "sonner";

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
  removeMsg: (s: string, id: string) => void;
  setCurrent: (id: string) => void;
  newSession: () => string;
  deleteSession: (id: string) => void;
  renameSession: (id: string, title: string) => void;
  clearAll: () => void;
}

const newId = () => Math.random().toString(36).slice(2, 10);
const now = () => Date.now();

const useChat = create<ChatState>()(
  persist(
    (set, get) => ({
      sessions: [
        {
          id: newId(),
          title: "محادثة جديدة",
          messages: [
            {
              id: newId(),
              role: "assistant",
              ts: now(),
              content:
                "أهلاً 👋 أنا مساعد محرك الـLeads.\n\nأقدر:\n- أشغّل لك خط توليد leads في أي مدينة سعودية\n- أفحص أي إيميل (5 حالات: Deliverable/Risky/Catch-all/Invalid/Unknown)\n- أعطيك حالة النظام والمهام والـleads\n\nجرّب تطلب: *«اعمل ليد جينيراشن في الرياض»*",
            },
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
      removeMsg: (sid, id) =>
        set((s) => ({
          sessions: s.sessions.map((x) =>
            x.id === sid ? { ...x, messages: x.messages.filter((m) => m.id !== id) } : x
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
                {
                  id: newId(),
                  role: "assistant",
                  ts: now(),
                  content: "جاهز للطلب — اكتب أي شيء تريد تنفيذه.",
                },
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
          return {
            sessions: remaining,
            currentId: remaining[0]?.id ?? "",
          };
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

// ===== API =====
async function sendChat(messages: { role: string; content: string }[]): Promise<{
  reply: string;
  provider?: string;
  tools?: ToolCall[];
}> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(t || `HTTP ${res.status}`);
  }
  return res.json();
}

// ===== Page =====
const QUICK_PROMPTS = [
  {
    icon: Globe2,
    title: "توليد leads في الرياض",
    prompt: "اعمل ليد جينيراشن في الرياض — عيادات أسنان (الافتراضي 30 ليد)",
  },
  {
    icon: ListChecks,
    title: "عرض آخر 10 leads",
    prompt: "اعرض آخر 10 leads مقبولة من قاعدة البيانات",
  },
  {
    icon: Mail,
    title: "فحص إيميل",
    prompt: "افحص الإيميل: info@clinic.sa",
  },
  {
    icon: Activity,
    title: "حالة النظام",
    prompt: "إيش حالة النظام والمزوّدين الحين؟",
  },
];

export function ChatPage() {
  const { sessions, currentId, addMsg, updateMsg, setCurrent, newSession, deleteSession, clearAll } = useChat();
  const session = sessions.find((s) => s.id === currentId) || sessions[0];

  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!currentId && sessions[0]) setCurrent(sessions[0].id);
  }, [currentId, sessions, setCurrent]);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [session?.messages.length, session?.messages[session.messages.length - 1]?.content]);

  async function send(text: string) {
    if (!text.trim() || !session || busy) return;
    const userMsg: Msg = { id: newId(), role: "user", content: text.trim(), ts: now() };
    addMsg(session.id, userMsg);
    setInput("");
    setBusy(true);

    // Auto-title from first user message
    if (session.messages.length <= 1) {
      const title = text.trim().slice(0, 40);
      useChat.getState().renameSession(session.id, title);
    }

    const pendingId = newId();
    addMsg(session.id, {
      id: pendingId,
      role: "assistant",
      content: "",
      ts: now(),
      pending: true,
    });

    abortRef.current = new AbortController();
    try {
      const apiMsgs = [...session.messages, userMsg].map((m) => ({
        role: m.role,
        content: m.content,
      }));
      const data = await sendChat(apiMsgs);
      updateMsg(session.id, pendingId, {
        content: data.reply || "(رد فارغ)",
        tools: data.tools || [],
        pending: false,
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

  if (!session) {
    return <div className="text-center text-[var(--fg-muted)] py-20">لا توجد محادثات</div>;
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-4 h-[calc(100vh-9rem)]">
      {/* Sessions sidebar */}
      <Card className="hidden lg:flex flex-col p-3">
        <div className="flex items-center justify-between mb-3 px-1">
          <h2 className="text-sm font-semibold flex items-center gap-1.5">
            <Bot className="h-4 w-4 text-[var(--accent)]" />
            المحادثات
          </h2>
          <Button size="icon-sm" variant="ghost" onClick={() => newSession()} title="محادثة جديدة">
            <Plus className="h-4 w-4" />
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto space-y-1">
          {sessions.map((s) => (
            <button
              key={s.id}
              onClick={() => setCurrent(s.id)}
              className={cn(
                "w-full text-right rounded-lg px-3 py-2 text-xs transition-colors group flex items-start gap-2",
                s.id === currentId
                  ? "bg-[var(--accent-soft)] text-[var(--accent-hover)]"
                  : "text-[var(--fg-muted)] hover:bg-[var(--bg-hover)]"
              )}
            >
              <div className="flex-1 min-w-0">
                <div className="font-medium truncate">{s.title || "بدون عنوان"}</div>
                <div className="text-[10px] text-[var(--fg-soft)] mt-0.5">
                  {s.messages.length} رسالة
                </div>
              </div>
              {sessions.length > 1 && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    if (confirm("حذف المحادثة؟")) deleteSession(s.id);
                  }}
                  className="opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-[var(--danger)]/20 rounded"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              )}
            </button>
          ))}
        </div>
        {sessions.length > 0 && (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              if (confirm("حذف كل المحادثات؟")) clearAll();
            }}
            className="mt-2 text-[var(--danger)]"
          >
            <Trash2 className="h-3.5 w-3.5" />
            مسح الكل
          </Button>
        )}
      </Card>

      {/* Chat panel */}
      <Card className="flex flex-col overflow-hidden">
        {/* Header */}
        <div className="border-b border-[var(--border)] p-4 flex items-center gap-3">
          <div className="h-9 w-9 rounded-lg bg-[image:var(--gradient)] flex items-center justify-center">
            <Sparkles className="h-4.5 w-4.5 text-white" />
          </div>
          <div>
            <h1 className="font-semibold text-sm flex items-center gap-2">
              مساعد محرك الـLeads
              <Badge variant="accent" className="text-[10px]">Gemini · Tools</Badge>
            </h1>
            <p className="text-[11px] text-[var(--fg-muted)]">
              مفاتيحك الحقيقية — تنفيذ مباشر بدون تخمين
            </p>
          </div>
        </div>

        {/* Log */}
        <div ref={logRef} className="flex-1 overflow-y-auto p-4 space-y-4">
          {session.messages.length === 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-w-3xl mx-auto pt-8">
              {QUICK_PROMPTS.map((qp, i) => {
                const Icon = qp.icon;
                return (
                  <button
                    key={i}
                    onClick={() => send(qp.prompt)}
                    disabled={busy}
                    className="text-right rounded-xl p-4 bg-[var(--bg-soft)] border border-[var(--border)] hover:border-[var(--accent)] hover:bg-[var(--accent-soft)] transition-all group"
                  >
                    <Icon className="h-5 w-5 mb-2 text-[var(--accent)]" />
                    <div className="font-medium text-sm">{qp.title}</div>
                    <div className="text-xs text-[var(--fg-muted)] mt-1">{qp.prompt}</div>
                  </button>
                );
              })}
            </div>
          )}

          {session.messages.map((m) => (
            <MessageBubble key={m.id} msg={m} />
          ))}
        </div>

        {/* Input */}
        <div className="border-t border-[var(--border)] p-3 bg-[var(--bg-soft)]">
          <div className="flex items-end gap-2 max-w-4xl mx-auto">
            <div className="flex-1 relative">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={onKey}
                rows={1}
                placeholder="اكتب طلبك… (Enter للإرسال · Shift+Enter سطر جديد)"
                disabled={busy}
                className="w-full resize-none rounded-xl border border-[var(--border)] bg-[var(--bg-elev)] px-4 py-3 pe-12 text-sm focus:outline-none focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--ring)] disabled:opacity-50 max-h-32"
              />
            </div>
            {busy ? (
              <Button variant="danger" size="icon" onClick={stop}>
                <Square className="h-4 w-4" />
              </Button>
            ) : (
              <Button
                variant="primary"
                size="icon"
                onClick={() => send(input)}
                disabled={!input.trim()}
              >
                <Send className="h-4 w-4" />
              </Button>
            )}
          </div>
          <p className="text-[10px] text-[var(--fg-soft)] text-center mt-2">
            <Lightbulb className="inline h-3 w-3" /> الأوامر تستخدم مفاتيحك الحقيقية — التنفيذ يكلف رصيد من المزوّدين.
          </p>
        </div>
      </Card>
    </div>
  );
}

function MessageBubble({ msg }: { msg: Msg }) {
  const isUser = msg.role === "user";
  return (
    <div className={cn("flex gap-3 animate-slide-up", isUser ? "flex-row-reverse" : "flex-row")}>
      <div
        className={cn(
          "h-8 w-8 rounded-full flex items-center justify-center shrink-0",
          isUser
            ? "bg-[var(--bg-soft)] border border-[var(--border)]"
            : "bg-[image:var(--gradient)]"
        )}
      >
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4 text-white" />}
      </div>

      <div className={cn("flex-1 min-w-0 space-y-2", isUser ? "text-right" : "text-right")}>
        <div className="text-[10px] text-[var(--fg-soft)] flex items-center gap-2">
          <span className="font-semibold text-[var(--fg-muted)]">
            {isUser ? "أنت" : "المساعد"}
          </span>
          {new Date(msg.ts).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })}
        </div>

        {msg.pending ? (
          <div className="inline-flex items-center gap-2 rounded-2xl bg-[var(--bg-soft)] px-4 py-3 border border-[var(--border)]">
            <Loader2 className="h-3.5 w-3.5 animate-spin text-[var(--accent)]" />
            <span className="text-sm text-[var(--fg-muted)]">يفكّر…</span>
          </div>
        ) : msg.error ? (
          <div className="rounded-2xl border border-[var(--danger)]/40 bg-[var(--danger)]/10 px-4 py-3">
            <div className="flex items-center gap-2 text-[var(--danger)] text-sm font-medium">
              <XCircle className="h-4 w-4" /> فشل
            </div>
            <div className="text-xs text-[var(--fg-muted)] mt-1">{msg.error}</div>
          </div>
        ) : (
          <div
            className={cn(
              "rounded-2xl px-4 py-3 max-w-3xl inline-block",
              isUser
                ? "bg-[var(--accent)] text-white"
                : "bg-[var(--bg-soft)] border border-[var(--border)]"
            )}
          >
            {isUser ? (
              <div className="text-sm whitespace-pre-wrap break-words">{msg.content}</div>
            ) : (
              <div className="md-body text-sm text-[var(--fg)]">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
              </div>
            )}
          </div>
        )}

        {msg.tools && msg.tools.length > 0 && (
          <details className="rounded-xl border border-[var(--border)] bg-[var(--bg-soft)] overflow-hidden text-xs">
            <summary className="cursor-pointer px-3 py-2 font-medium flex items-center gap-2 hover:bg-[var(--bg-hover)]">
              <Wrench className="h-3.5 w-3.5 text-[var(--accent)]" />
              {msg.tools.length} أداة تم تنفيذها
            </summary>
            <div className="p-3 space-y-2 border-t border-[var(--border)]">
              {msg.tools.map((t, i) => (
                <div
                  key={i}
                  className="rounded-lg p-2 bg-[var(--bg-elev)] border border-[var(--border-soft)]"
                >
                  <div className="flex items-center gap-2 font-medium">
                    {t.ok ? (
                      <CheckCircle2 className="h-3.5 w-3.5 text-[var(--success)]" />
                    ) : (
                      <XCircle className="h-3.5 w-3.5 text-[var(--danger)]" />
                    )}
                    <span dir="ltr">{t.name}</span>
                  </div>
                  {Object.keys(t.args || {}).length > 0 && (
                    <pre className="mt-1.5 text-[11px] text-[var(--fg-muted)] whitespace-pre-wrap">
                      {JSON.stringify(t.args, null, 2)}
                    </pre>
                  )}
                  {t.summary && (
                    <pre className="mt-1.5 text-[11px] text-[var(--fg-muted)] whitespace-pre-wrap max-h-32 overflow-auto">
                      {t.summary}
                    </pre>
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
