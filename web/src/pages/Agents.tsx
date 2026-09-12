import { useEffect, useMemo, useState } from "react";
import {
  Bot, CheckCircle2, Clock3, History, Play, RefreshCw, ShieldCheck,
  Wrench, XCircle, X, Check, Coins, Plus, Sparkles, Cpu,
} from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Input, Textarea, Select, Label } from "@/components/ui/Input";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/Dialog";
import { apiGet, apiPost } from "@/lib/api";
import { toast } from "sonner";
import { friendlyError, ACTION_LABELS, describePayload, toolLabel } from "@/lib/friendly";
import { cn, formatNumber, relativeTime } from "@/lib/utils";
import { PageHeader } from "@/components/layout/PageHeader";
import { Spinner, EmptyState } from "@/components/ui/EmptyState";

type Agent = { slug: string; name: string; description: string; status: string; current_version: string };
type AgentRun = { run_id: string; slug: string; name: string; version: string; status: string; cost_usd?: number; prompt_tokens?: number; completion_tokens?: number; created_at?: string; updated_at?: string; error?: string | null };
type Tool = { name: string; description: string; scopes?: string; requires_approval: number };
type Approval = { approval_id: string; action: string; status: string; requested_at?: string; payload_json?: string };

export function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [tools, setTools] = useState<Tool[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [busyApproval, setBusyApproval] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const [agentData, runData, toolData, approvalData] = await Promise.all([
        apiGet.agents(), apiGet.agentRuns(), apiGet.tools(), apiGet.approvals(),
      ]);
      setAgents(agentData.agents);
      setRuns(runData.runs);
      setTools(toolData.tools);
      setApprovals(approvalData.approvals);
    } catch (error: unknown) {
      toast.error(friendlyError(error));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function runAgent() {
    setRunning(true);
    try {
      await apiPost.runBenchmark({ icp: "v0_saudi_dental" });
      toast.success("بدأ تشغيل الوكيل — تابع حالته من صفحة المهام");
      await load();
    } catch (error: unknown) {
      toast.error(friendlyError(error));
    } finally {
      setRunning(false);
    }
  }

  async function resolve(id: string, status: "APPROVED" | "REJECTED") {
    setBusyApproval(id);
    try {
      await apiPost.resolveApproval(id, status);
      toast.success(status === "APPROVED" ? "تمت الموافقة — التشغيل هيكمل" : "تم الرفض");
      await load();
    } catch (e) {
      toast.error(friendlyError(e));
    } finally {
      setBusyApproval(null);
    }
  }

  const totalTokens = runs.reduce((sum, run) => sum + (run.prompt_tokens || 0) + (run.completion_tokens || 0), 0);

  // Aggregate tool scopes for the picker (deduped, alphabetical)
  const allScopes = useMemo(() => {
    const set = new Set<string>();
    tools.forEach((t) => {
      try {
        const scopes = t.scopes ? (typeof t.scopes === "string" ? JSON.parse(t.scopes) : t.scopes) : [];
        (Array.isArray(scopes) ? scopes : []).forEach((s) => set.add(String(s)));
      } catch { /* ignore malformed */ }
    });
    return Array.from(set).sort();
  }, [tools]);

  return (
    <div className="space-y-5">
      <PageHeader
        icon={<Bot className="h-4 w-4 text-white" />}
        title="لوحة الوكلاء"
        description="التشغيل الحي للمساعد محتاج موافقة من هنا — والإصدارات والأدوات والتكلفة كلها أمامك"
        action={
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => setCreateOpen(true)}>
              <Plus className="h-3.5 w-3.5" />
              إنشاء وكيل
            </Button>
            <Button variant="outline" size="sm" onClick={load} disabled={loading}>
              <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
              تحديث
            </Button>
            <Button variant="primary" size="sm" onClick={runAgent} loading={running}>
              <Play className="h-3.5 w-3.5" />
              تشغيل مهمة حقيقية
            </Button>
          </div>
        }
      />

      {/* Pending approvals — the most important block, first */}
      <Card className={cn(approvals.length > 0 && "border-[var(--warn)]/50")}>
        <div className="p-5">
          <div className="flex items-center gap-2 mb-4">
            <ShieldCheck className={cn("h-4 w-4", approvals.length ? "text-[var(--warn)]" : "text-[var(--success)]")} />
            <h2 className="text-sm font-bold">طلبات الموافقة</h2>
            {approvals.length > 0 && <Badge variant="warn" className="text-[10px] tnum">{approvals.length} معلقة</Badge>}
          </div>
          {approvals.length === 0 ? (
            <div className="text-center py-6">
              <CheckCircle2 className="h-8 w-8 text-[var(--success)] mx-auto mb-3 opacity-70" />
              <p className="text-sm text-[var(--fg-muted)]">مفيش موافقات مستنية — التشغيلات العادية ماشية تلقائي</p>
              <p className="text-[11px] text-[var(--fg-soft)] mt-1">لما يطلب المساعد الذكي تشغيل حي من الشات، هتلاقي الطلب هنا</p>
            </div>
          ) : (
            <div className="space-y-2">
              {approvals.map((a) => (
                <div key={a.approval_id} className="rounded-xl border border-[var(--warn)]/40 bg-[var(--warn)]/5 p-4">
                  <div className="flex items-start justify-between gap-3 flex-wrap">
                    <div className="min-w-0">
                      <div className="text-[13px] font-semibold">{ACTION_LABELS[a.action] ?? a.action.replace(/_/g, " ")}</div>
                      {(() => {
                        let payload: unknown = a.payload_json;
                        if (typeof payload === "string") { try { payload = JSON.parse(payload); } catch { /* keep raw */ } }
                        const rows = describePayload(payload);
                        if (!rows.length) return null;
                        return (
                          <div className="mt-1.5 rounded-lg bg-[var(--bg-soft)] border border-[var(--border-soft)] p-2.5 space-y-1">
                            {rows.map((r, i) => (
                              <div key={i} className="flex items-center justify-between gap-3 text-[12px]">
                                <span className="text-[var(--fg-muted)]">{r.label}</span>
                                <span className="font-medium truncate max-w-[60%]">{r.value}</span>
                              </div>
                            ))}
                          </div>
                        );
                      })()}
                      <div className="text-[11px] text-[var(--fg-soft)] mt-2">
                        مطلوبة {a.requested_at ? `منذ ${relativeTime(a.requested_at)}` : "الآن"}
                      </div>
                    </div>
                    <div className="flex gap-2 shrink-0">
                      <Button size="sm" variant="primary" disabled={busyApproval === a.approval_id} onClick={() => resolve(a.approval_id, "APPROVED")}>
                        <Check className="h-3.5 w-3.5" />
                        موافقة
                      </Button>
                      <Button size="sm" variant="outline" disabled={busyApproval === a.approval_id} onClick={() => resolve(a.approval_id, "REJECTED")}>
                        <X className="h-3.5 w-3.5" />
                        رفض
                      </Button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </Card>

      {/* Stats */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
        <Metric icon={Bot} label="وكلاء مسجلون" value={agents.length} detail="بتعريفات وإصدارات" />
        <Metric icon={History} label="التشغيلات" value={runs.length} detail="آخر 50" />
        <Metric icon={Wrench} label="أدوات مكشوفة" value={tools.length} detail="بصلاحيات محددة" />
        <Metric icon={Coins} label="التوكنز المستهلكة" value={totalTokens} detail="تشغيلات الوكلاء" />
      </div>

      {/* Agents + runs */}
      <div className="grid xl:grid-cols-[1fr_1.4fr] gap-4 items-start">
        <Card className="p-5">
          <div className="flex items-center gap-2 mb-4">
            <Bot className="h-4 w-4 text-[var(--accent)]" />
            <h2 className="text-sm font-bold">الوكلاء والإصدارات</h2>
          </div>
          {agents.length === 0 ? (
            <EmptyState icon={<Bot className="h-8 w-8" />} title="لا وكلاء مسجلين" description="هتلاقي الوكيل الافتراضي بعد أول تشغيل" />
          ) : (
            <div className="space-y-2.5">
              {agents.map((agent) => (
                <div key={agent.slug} className="rounded-xl border border-[var(--border-soft)] bg-[var(--bg-soft)] p-3.5">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-semibold text-[13px]">{agent.name}</div>
                      <div className="text-xs text-[var(--fg-muted)] mt-1 leading-5">{agent.description}</div>
                    </div>
                    <Badge variant="success" className="text-[10px] shrink-0">
                      <CheckCircle2 className="h-3 w-3" />
                      نشط
                    </Badge>
                  </div>
                  <div className="flex items-center gap-2 mt-2.5 text-[11px] text-[var(--fg-muted)]">
                    <span>الإصدار {agent.current_version}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card className="p-0 overflow-hidden">
          <div className="flex items-center gap-2 px-5 h-12 border-b border-[var(--border)]">
            <History className="h-4 w-4 text-[var(--accent)]" />
            <h2 className="text-sm font-bold">آخر التشغيلات</h2>
          </div>
          {loading ? (
            <div className="flex justify-center py-14"><Spinner className="h-6 w-6 text-[var(--accent)]" /></div>
          ) : runs.length === 0 ? (
            <EmptyState icon={<History className="h-8 w-8" />} title="لا تشغيلات بعد" description="شغّل مهمة من الزر أعلى الصفحة أو من المساعد الذكي" />
          ) : (
            <div className="overflow-x-auto">
              <table className="pro-table">
                <thead>
                  <tr>
                    <th>الوكيل</th>
                    <th>الحالة</th>
                    <th>التوكنز</th>
                    <th>الوقت</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((run) => (
                    <tr key={run.run_id}>
                      <td>
                        <div className="font-medium text-[13px]">{run.name || "وكيل المنصة"}</div>
                        <span className="text-[10px] text-[var(--fg-soft)]">إصدار {run.version}</span>
                      </td>
                      <td><RunBadge status={run.status} /></td>
                      <td className="tnum text-xs" dir="ltr">{formatNumber((run.prompt_tokens || 0) + (run.completion_tokens || 0))}</td>
                      <td className="text-xs text-[var(--fg-muted)]">{run.created_at ? relativeTime(run.created_at) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      {/* Tools registry */}
      <Card className="p-5">
        <div className="flex items-center gap-2 mb-4">
          <Wrench className="h-4 w-4 text-[var(--accent)]" />
          <h2 className="text-sm font-bold">سجل الأدوات</h2>
          <span className="text-[11px] text-[var(--fg-soft)]">الأداة مش بتتكشف للوكيل غير بصلاحياتها</span>
        </div>
        <div className="grid md:grid-cols-2 gap-2.5">
          {tools.map((tool) => (
            <div key={tool.name} className="flex items-center justify-between gap-3 rounded-xl border border-[var(--border-soft)] bg-[var(--bg-soft)] p-3">
              <div className="min-w-0">
                <span className="text-[13px] font-semibold text-[var(--accent)]">{toolLabel(tool.name)}</span>
                <div className="text-[11px] text-[var(--fg-muted)] mt-1 truncate">{tool.description}</div>
              </div>
              {tool.requires_approval
                ? <Badge variant="warn" className="text-[10px] shrink-0"><ShieldCheck className="h-3 w-3" /> موافقة</Badge>
                : <Badge variant="outline" className="text-[10px] shrink-0">مباشر</Badge>}
            </div>
          ))}
        </div>
      </Card>

      <CreateAgentDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        scopes={allScopes}
        onCreated={() => { load(); }}
      />
    </div>
  );
}

function Metric({ icon: Icon, label, value, detail }: { icon: typeof Bot; label: string; value: number; detail: string }) {
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between mb-2.5">
        <span className="text-xs text-[var(--fg-muted)]">{label}</span>
        <Icon className="h-4 w-4 text-[var(--accent)]" />
      </div>
      <div className="text-xl font-bold tnum">{formatNumber(value)}</div>
      <div className="text-[11px] text-[var(--fg-soft)] mt-1">{detail}</div>
    </Card>
  );
}

function RunBadge({ status }: { status: string }) {
  const normalized = status.toUpperCase();
  if (["COMPLETED", "ACCEPTED"].includes(normalized)) return <Badge variant="success" className="text-[10px]"><CheckCircle2 className="h-3 w-3" /> مكتمل</Badge>;
  if (["FAILED", "REJECTED"].includes(normalized)) return <Badge variant="danger" className="text-[10px]"><XCircle className="h-3 w-3" /> فاشل</Badge>;
  return <Badge variant="warn" className="text-[10px]"><Clock3 className="h-3 w-3" /> جاري</Badge>;
}

const MODEL_PROVIDERS = [
  { value: "router", label: "تلقائي (Router)", desc: "يختار الأنسب حسب التوفر والحصص" },
  { value: "gemini", label: "Gemini", desc: "Google — سريع ورخيص" },
  { value: "groq", label: "Groq", desc: "سريع جداً — latency منخفض" },
  { value: "openrouter", label: "OpenRouter", desc: "أي نموذج عبر API واحد" },
  { value: "ollama", label: "Ollama (محلي)", desc: "يشتغل بدون إنترنت" },
] as const;

const EFFORT_LEVELS = [
  { value: "", label: "افتراضي", desc: "النموذج يقرر" },
  { value: "low", label: "منخفض", desc: "أسرع، أرخص" },
  { value: "medium", label: "متوسط", desc: "توازن" },
  { value: "high", label: "عالي", desc: "أعمق، أبطأ" },
  { value: "max", label: "أقصى", desc: "للتفكير المعقد" },
] as const;

function slugify(name: string): string {
  // Hidden from the user — generated internally, ASCII-safe for the API.
  const base = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40);
  const suffix = Math.random().toString(36).slice(2, 6);
  return (base.length >= 2 ? base : "agent") + "-" + suffix;
}

function CreateAgentDialog({
  open, onOpenChange, scopes, onCreated,
}: {
  open: boolean;
  onOpenChange: (b: boolean) => void;
  scopes: string[];
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [description, setDescription] = useState("");
  const [instructions, setInstructions] = useState("");
  const [modelProvider, setModelProvider] = useState<string>("router");
  const [modelName, setModelName] = useState("");
  const [thinkingEffort, setThinkingEffort] = useState<string>("");
  const [selectedScopes, setSelectedScopes] = useState<Set<string>>(new Set());
  const [submitting, setSubmitting] = useState(false);

  // Slug is generated internally at submit time — users only pick a name.
  useEffect(() => {
    if (open && name.trim()) setSlug(slugify(name));
  }, [open, name]);

  // Reset form when dialog closes
  useEffect(() => {
    if (!open) {
      setName(""); setSlug("");
      setDescription(""); setInstructions("");
      setModelProvider("router"); setModelName("");
      setThinkingEffort(""); setSelectedScopes(new Set());
    }
  }, [open]);

  const requiresModelName = modelProvider === "openrouter" || modelProvider === "ollama";
  const formValid = name.trim().length >= 1 &&
    /^[a-z0-9][a-z0-9_-]*$/.test(slug) &&
    slug.length >= 2 &&
    (!requiresModelName || modelName.trim().length >= 1);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!formValid) return;
    setSubmitting(true);
    try {
      await apiPost.createAgent({
        slug, name: name.trim(),
        description: description.trim(),
        status: "active",
      });
      await apiPost.createAgentVersion(slug, {
        version: "1.0.0",
        instructions: instructions.trim() || undefined,
        model_provider: modelProvider,
        model_name: modelName.trim() || undefined,
        thinking_effort: thinkingEffort || undefined,
        tool_policy: selectedScopes.size > 0 ? { scopes: Array.from(selectedScopes) } : undefined,
        activate: true,
      });
      toast.success(`تم إنشاء الوكيل "${name.trim()}" وتفعيله`);
      onOpenChange(false);
      onCreated();
    } catch (err: any) {
      toast.error(err?.message || "فشل إنشاء الوكيل");
    } finally {
      setSubmitting(false);
    }
  }

  function toggleScope(s: string) {
    setSelectedScopes((prev) => {
      const next = new Set(prev);
      if (next.has(s)) next.delete(s);
      else next.add(s);
      return next;
    });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-[var(--accent)]" />
            إنشاء وكيل جديد
          </DialogTitle>
          <DialogDescription>
            وكيل متخصص يقدر الشات استدعاؤه. اختار النموذج وقوة التفكير والأدوات المسموحة.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 mt-2">
          <div className="space-y-1.5">
            <Label htmlFor="agent-name">اسم الوكيل</Label>
            <Input
              id="agent-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="مثل: وكيل تأهيل العملاء المحتملين"
              autoFocus
              dir="rtl"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="agent-desc">الوصف</Label>
            <Input
              id="agent-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="سطر واحد يوضح متى يُستخدم هذا الوكيل"
              dir="rtl"
            />
          </div>

          <div className="space-y-1.5">
              <Label htmlFor="agent-instructions">
              التعليمات
              <span className="text-[10px] text-[var(--fg-soft)] mr-1">(اختياري — بتحدد شخصية الوكيل وطريقة كلامه)</span>
            </Label>
            <Textarea
              id="agent-instructions"
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              placeholder="أنت وكيل تأهيل leads. تتكلم بالعربية. تركز على الشركات في الرياض..."
              rows={3}
              dir="rtl"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="agent-provider" className="flex items-center gap-1.5">
                <Cpu className="h-3 w-3" /> مزوّد النموذج
              </Label>
              <Select
                id="agent-provider"
                value={modelProvider}
                onChange={(e) => setModelProvider(e.target.value)}
                dir="rtl"
              >
                {MODEL_PROVIDERS.map((p) => (
                  <option key={p.value} value={p.value}>{p.label} — {p.desc}</option>
                ))}
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="agent-effort">قوة التفكير</Label>
              <Select
                id="agent-effort"
                value={thinkingEffort}
                onChange={(e) => setThinkingEffort(e.target.value)}
                dir="rtl"
              >
                {EFFORT_LEVELS.map((l) => (
                  <option key={l.value} value={l.value}>{l.label} — {l.desc}</option>
                ))}
              </Select>
            </div>
          </div>

          {requiresModelName && (
            <div className="space-y-1.5">
              <Label htmlFor="agent-model">اسم النموذج</Label>
              <Input
                id="agent-model"
                value={modelName}
                onChange={(e) => setModelName(e.target.value)}
                placeholder={modelProvider === "openrouter" ? "anthropic/claude-sonnet-4.5" : "llama3.1:8b"}
                dir="ltr"
                className="font-mono text-xs"
              />
            </div>
          )}

          {scopes.length > 0 && (
            <div className="space-y-2">
              <Label>الأدوات المسموحة للوكيل</Label>
              <div className="flex flex-wrap gap-1.5">
                {scopes.map((s) => {
                  const active = selectedScopes.has(s);
                  return (
                    <button
                      key={s}
                      type="button"
                      onClick={() => toggleScope(s)}
                      dir="ltr"
                      className={cn(
                        "px-2.5 h-7 rounded-full text-[11px] font-medium border transition-colors",
                        active
                          ? "bg-[var(--accent-soft)] border-[var(--accent)] text-[var(--accent)]"
                          : "bg-[var(--bg-soft)] border-[var(--border-soft)] text-[var(--fg-muted)] hover:border-[var(--border)]"
                      )}
                    >
                      {active && <Check className="inline h-3 w-3 ml-1" />}
                      {toolLabel(s)}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2 border-t border-[var(--border-soft)]">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
              إلغاء
            </Button>
            <Button type="submit" variant="primary" loading={submitting} disabled={!formValid}>
              <Sparkles className="h-3.5 w-3.5" />
              إنشاء وتفعيل
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
