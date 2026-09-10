import { useEffect, useState } from "react";
import {
  Activity,
  Bot,
  CheckCircle2,
  Clock3,
  History,
  KeyRound,
  Play,
  RefreshCw,
  ShieldCheck,
  Wrench,
  XCircle,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { apiGet, apiPost } from "@/lib/api";
import { toast } from "sonner";
import { cn, formatNumber, relativeTime } from "@/lib/utils";

type Agent = { slug: string; name: string; description: string; status: string; current_version: string };
type AgentRun = { run_id: string; slug: string; name: string; version: string; status: string; cost_usd?: number; prompt_tokens?: number; completion_tokens?: number; created_at?: string; updated_at?: string; error?: string | null };
type Tool = { name: string; description: string; scopes?: string; requires_approval: number };
type Approval = { approval_id: string; action: string; status: string; requested_at?: string };

export function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [tools, setTools] = useState<Tool[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);

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
    } catch (error: any) {
      toast.error(error.message || "تعذر تحميل بيانات الوكلاء");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function runAgentTest() {
    setRunning(true);
    try {
      await apiPost.runBenchmark({ icp: "v0_saudi_dental" });
      toast.success("تم تشغيل مهمة الوكيل");
      await load();
    } catch (error: any) {
      toast.error(error.message || "فشل تشغيل الوكيل");
    } finally {
      setRunning(false);
    }
  }

  const totalTokens = runs.reduce((sum, run) => sum + (run.prompt_tokens || 0) + (run.completion_tokens || 0), 0);

  return (
    <div className="space-y-6">
      <header className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold text-[var(--accent)] mb-2"><Bot className="h-4 w-4" /> مركز الوكلاء</div>
          <h1 className="text-2xl font-bold">Agents Control Plane</h1>
          <p className="text-sm text-[var(--fg-muted)] mt-1 max-w-2xl">إصدارات الوكلاء، التشغيلات، الأدوات، والموافقات في شاشة تشغيل واحدة.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={load} disabled={loading}><RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} /> تحديث</Button>
          <Button variant="primary" onClick={runAgentTest} loading={running}><Play className="h-4 w-4" /> تشغيل مهمة حقيقية</Button>
        </div>
      </header>

      <section className="grid grid-cols-2 xl:grid-cols-4 gap-3">
        <Metric icon={Bot} label="الوكلاء" value={agents.length} detail="تعريفات مسجلة" />
        <Metric icon={History} label="التشغيلات" value={runs.length} detail="آخر 50 تشغيل" />
        <Metric icon={Wrench} label="الأدوات" value={tools.length} detail="بصلاحيات محددة" />
        <Metric icon={KeyRound} label="Tokens" value={totalTokens} detail={`${approvals.length} موافقة معلقة`} tone={approvals.length ? "warn" : "success"} />
      </section>

      <section className="grid xl:grid-cols-[1fr_1.4fr] gap-4">
        <Card>
          <CardHeader><CardTitle><Bot className="h-4 w-4 text-[var(--accent)]" /> الوكلاء والإصدارات</CardTitle><CardDescription>كل Agent له version قابلة للتتبع.</CardDescription></CardHeader>
          <CardContent className="space-y-3">
            {agents.map((agent) => <div key={agent.slug} className="rounded-lg border border-[var(--border-soft)] bg-[var(--bg-soft)] p-4">
              <div className="flex items-start justify-between gap-3"><div><div className="font-semibold text-sm">{agent.name}</div><div className="text-xs text-[var(--fg-muted)] mt-1">{agent.description}</div></div><Badge variant="success"><CheckCircle2 className="h-3 w-3" /> {agent.status}</Badge></div>
              <div className="flex items-center gap-2 mt-3 text-xs text-[var(--fg-muted)]"><span>الإصدار الحالي</span><code dir="ltr">v{agent.current_version}</code></div>
            </div>)}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle><History className="h-4 w-4 text-[var(--accent)]" /> آخر التشغيلات</CardTitle><CardDescription>كل تشغيل يحتفظ بالنسخة والتكلفة والنتيجة.</CardDescription></CardHeader>
          <CardContent className="p-0"><div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="border-b border-[var(--border)] bg-[var(--bg-soft)]"><th className="text-right p-3">الوكيل</th><th className="text-right p-3">الحالة</th><th className="text-right p-3">Tokens</th><th className="text-right p-3">الوقت</th></tr></thead><tbody>{runs.length === 0 ? <tr><td colSpan={4} className="p-8 text-center text-sm text-[var(--fg-muted)]">لا توجد تشغيلات بعد</td></tr> : runs.map((run) => <tr key={run.run_id} className="border-b border-[var(--border-soft)]"><td className="p-3"><div className="font-medium">{run.name || run.slug}</div><code className="text-[10px]">v{run.version}</code></td><td className="p-3"><RunBadge status={run.status} /></td><td className="p-3 tabular-nums" dir="ltr">{formatNumber((run.prompt_tokens || 0) + (run.completion_tokens || 0))}</td><td className="p-3 text-xs text-[var(--fg-muted)]">{run.created_at ? relativeTime(run.created_at) : "-"}</td></tr>)}</tbody></table></div></CardContent>
        </Card>
      </section>

      <section className="grid lg:grid-cols-2 gap-4">
        <Card><CardHeader><CardTitle><Wrench className="h-4 w-4 text-[var(--accent)]" /> Tool Registry</CardTitle><CardDescription>الأداة لا تُكشف للوكيل إلا بصلاحياتها.</CardDescription></CardHeader><CardContent className="space-y-2">{tools.map((tool) => <div key={tool.name} className="flex items-center justify-between gap-3 rounded-lg border border-[var(--border-soft)] p-3"><div><code className="text-xs" dir="ltr">{tool.name}</code><div className="text-xs text-[var(--fg-muted)] mt-1">{tool.description}</div></div>{tool.requires_approval ? <Badge variant="warn"><ShieldCheck className="h-3 w-3" /> موافقة</Badge> : <Badge variant="outline">مباشر</Badge>}</div>)}</CardContent></Card>
        <Card><CardHeader><CardTitle><ShieldCheck className="h-4 w-4 text-[var(--warn)]" /> الموافقات المعلقة</CardTitle><CardDescription>عمليات حساسة يجب ألا تنفذ بصمت.</CardDescription></CardHeader><CardContent>{approvals.length === 0 ? <div className="py-8 text-center text-sm text-[var(--fg-muted)]">لا توجد موافقات معلقة</div> : <div className="space-y-2">{approvals.map((approval) => <div key={approval.approval_id} className="rounded-lg border border-[var(--warn)]/30 bg-[var(--warn)]/5 p-3"><div className="font-medium text-sm">{approval.action}</div><div className="text-xs text-[var(--fg-muted)] mt-1">مطلوبة منذ {approval.requested_at || "-"}</div></div>)}</div>}</CardContent></Card>
      </section>
    </div>
  );
}

function Metric({ icon: Icon, label, value, detail, tone = "accent" }: { icon: typeof Bot; label: string; value: number; detail: string; tone?: "accent" | "success" | "warn" }) {
  return <Card className="shadow-none"><CardContent className="p-4"><div className="flex items-center justify-between mb-3"><span className="text-xs text-[var(--fg-muted)]">{label}</span><Icon className={cn("h-4 w-4", tone === "warn" ? "text-[var(--warn)]" : tone === "success" ? "text-[var(--success)]" : "text-[var(--accent)]")} /></div><div className="text-xl font-bold tabular-nums">{value}</div><div className="text-[11px] text-[var(--fg-soft)] mt-1">{detail}</div></CardContent></Card>;
}

function RunBadge({ status }: { status: string }) {
  const normalized = status.toUpperCase();
  if (["COMPLETED", "ACCEPTED"].includes(normalized)) return <Badge variant="success"><CheckCircle2 className="h-3 w-3" /> {status}</Badge>;
  if (["FAILED", "REJECTED"].includes(normalized)) return <Badge variant="danger"><XCircle className="h-3 w-3" /> {status}</Badge>;
  return <Badge variant="warn"><Clock3 className="h-3 w-3" /> {status}</Badge>;
}
