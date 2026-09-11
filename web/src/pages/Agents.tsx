import { useEffect, useState } from "react";
import {
  Bot, CheckCircle2, Clock3, History, Play, RefreshCw, ShieldCheck,
  Wrench, XCircle, X, Check, Coins,
} from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { apiGet, apiPost } from "@/lib/api";
import { toast } from "sonner";
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

  async function runAgent() {
    setRunning(true);
    try {
      await apiPost.runBenchmark({ icp: "v0_saudi_dental" });
      toast.success("بدأ تشغيل الوكيل — تابع حالته من صفحة المهام");
      await load();
    } catch (error: any) {
      toast.error(error.message || "فشل تشغيل الوكيل");
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
    } catch (e: any) {
      toast.error(e.message || "فشل التنفيذ");
    } finally {
      setBusyApproval(null);
    }
  }

  const totalTokens = runs.reduce((sum, run) => sum + (run.prompt_tokens || 0) + (run.completion_tokens || 0), 0);

  return (
    <div className="space-y-5">
      <PageHeader
        icon={<Bot className="h-4 w-4 text-white" />}
        title="لوحة الوكلاء"
        description="التشغيل الحي للمساعد محتاج موافقة من هنا — والإصدارات والأدوات والتكلفة كلها أمامك"
        action={
          <div className="flex gap-2">
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
                      <div className="font-mono text-[13px] font-semibold" dir="ltr">{a.action}</div>
                      {a.payload_json && (
                        <pre className="mt-1.5 text-[11px] text-[var(--fg-muted)] max-h-20 overflow-auto rounded-lg bg-[var(--bg-soft)] border border-[var(--border-soft)] p-2" dir="ltr">{a.payload_json}</pre>
                      )}
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
                    <span>الإصدار</span>
                    <code dir="ltr" className="px-1.5 rounded bg-[var(--bg-elev)] border border-[var(--border-soft)]">v{agent.current_version}</code>
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
                        <div className="font-medium text-[13px]">{run.name || run.slug}</div>
                        <code className="text-[10px] text-[var(--fg-soft)]" dir="ltr">v{run.version}</code>
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
                <code className="text-xs font-semibold text-[var(--accent)]" dir="ltr">{tool.name}</code>
                <div className="text-[11px] text-[var(--fg-muted)] mt-1 truncate">{tool.description}</div>
              </div>
              {tool.requires_approval
                ? <Badge variant="warn" className="text-[10px] shrink-0"><ShieldCheck className="h-3 w-3" /> موافقة</Badge>
                : <Badge variant="outline" className="text-[10px] shrink-0">مباشر</Badge>}
            </div>
          ))}
        </div>
      </Card>
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
  if (["COMPLETED", "ACCEPTED"].includes(normalized)) return <Badge variant="success" className="text-[10px]"><CheckCircle2 className="h-3 w-3" /> {status}</Badge>;
  if (["FAILED", "REJECTED"].includes(normalized)) return <Badge variant="danger" className="text-[10px]"><XCircle className="h-3 w-3" /> {status}</Badge>;
  return <Badge variant="warn" className="text-[10px]"><Clock3 className="h-3 w-3" /> {status}</Badge>;
}
