import { useState } from "react";
import {
  Activity, Check, CheckCircle2, Clipboard, Code2, Database, ExternalLink,
  Globe2, Link2, Plug, RefreshCw, Webhook, Workflow, XCircle, Copy, Boxes,
} from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { useLiveData } from "@/hooks/useLiveData";
import { apiGet } from "@/lib/api";
import { toast } from "sonner";
import { cn, formatNumber } from "@/lib/utils";
import { PageHeader } from "@/components/layout/PageHeader";

const BACKEND_BASE = (import.meta.env.VITE_BACKEND_URL || window.location.origin).replace(/\/$/, "");
const MCP_URL = `${BACKEND_BASE}/mcp`;

const MCP_TOOLS = [
  { id: "run_lead_generation", desc: "خط توليد كامل لمدينة — بحث حقيقي + تأهيل AI" },
  { id: "list_leads", desc: "قراءة النتائج مع جهات الاتصال" },
  { id: "get_job_status", desc: "حالة أي مهمة وأحداثها" },
  { id: "verify_email", desc: "فحص بخمس حالات مع كشف catch-all" },
  { id: "system_status", desc: "المزودون والاستهلاك والحالة" },
];

export function IntegrationsPage() {
  const { data, loading, refresh } = useLiveData(() => apiGet.status(), 10000);
  const [testing, setTesting] = useState(false);
  const [mcpOnline, setMcpOnline] = useState<boolean | null>(null);

  const supabaseReady = Boolean(data?.system?.supabase_configured);
  const calls = (data?.usage_totals ?? []).reduce((sum, r) => sum + (r.units || 0), 0);

  async function copy(text: string, label: string) {
    await navigator.clipboard.writeText(text);
    toast.success(`تم نسخ ${label}`);
  }

  async function testMcp() {
    setTesting(true);
    try {
      const response = await fetch(MCP_URL, { headers: { Accept: "application/json" } });
      setMcpOnline(response.ok);
      toast[response.ok ? "success" : "error"](response.ok ? "خادم MCP يستجيب" : "خادم MCP غير متاح");
    } catch {
      setMcpOnline(false);
      toast.error("تعذر الوصول إلى خادم MCP");
    } finally {
      setTesting(false);
    }
  }

  const mcpConfig = JSON.stringify(
    { mcpServers: { "lead-engine": { url: MCP_URL, transport: "http" } } },
    null,
    2
  );

  return (
    <div className="space-y-6">
      <PageHeader
        icon={<Plug className="h-4 w-4 text-white" />}
        title="التكاملات و MCP"
        description="اربط المحرك بالأدوات الخارجية — نفس أدوات المساعد الذكي متاحة لأي عميل MCP"
        action={
          <Button variant="outline" size="sm" onClick={refresh} disabled={loading}>
            <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
            تحديث الحالة
          </Button>
        }
      />

      {/* ===== MCP server — the hero integration ===== */}
      <Card className="overflow-hidden">
        <div className="flex items-start justify-between gap-3 p-5 pb-4">
          <div className="flex items-start gap-3">
            <div className="h-10 w-10 rounded-xl bg-[var(--accent-soft)] text-[var(--accent)] flex items-center justify-center shrink-0">
              <Boxes className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="font-bold">خادم MCP</h2>
                <Badge variant={mcpOnline === false ? "danger" : "success"} className="text-[10px]">
                  {mcpOnline === false ? <XCircle className="h-3 w-3" /> : <CheckCircle2 className="h-3 w-3" />}
                  {mcpOnline === false ? "غير متاح" : "جاهز"}
                </Badge>
              </div>
              <p className="text-xs text-[var(--fg-muted)] mt-1">
                Model Context Protocol — وصّل Claude أو Cursor أو n8n أو أي عميل MCP على أدوات المحرك مباشرة.
              </p>
            </div>
          </div>
          <Button variant="primary" size="sm" onClick={testMcp} loading={testing} className="shrink-0">
            <Activity className="h-3.5 w-3.5" />
            اختبار الاتصال
          </Button>
        </div>

        <div className="px-5 pb-5 space-y-4">
          {/* URL row */}
          <div className="flex items-center gap-2 rounded-xl border border-[var(--border)] bg-[var(--bg-soft)] px-3.5 h-11" dir="ltr">
            <Globe2 className="h-4 w-4 text-[var(--fg-soft)] shrink-0" />
            <code className="text-xs truncate flex-1">{MCP_URL}</code>
            <Button variant="ghost" size="icon-sm" onClick={() => copy(MCP_URL, "الرابط")} title="نسخ الرابط">
              <Copy className="h-3.5 w-3.5" />
            </Button>
          </div>

          <div className="grid lg:grid-cols-2 gap-4">
            {/* Config snippet */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-[var(--fg-muted)]">إعداد جاهز للصق في أي عميل MCP</span>
                <Button variant="outline" size="sm" onClick={() => copy(mcpConfig, "الإعداد")}>
                  <Clipboard className="h-3 w-3" />
                  نسخ
                </Button>
              </div>
              <pre className="text-[11.5px] leading-5 rounded-lg border border-[var(--border)] bg-[var(--bg-soft)] p-3.5 overflow-x-auto" dir="ltr">{mcpConfig}</pre>
            </div>

            {/* Tools */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-[var(--fg-muted)]">الأدوات المكشوفة عبر MCP</span>
                <Badge variant="outline" className="text-[10px]">5 أدوات</Badge>
              </div>
              <div className="rounded-lg border border-[var(--border)] divide-y divide-[var(--border-soft)] overflow-hidden">
                {MCP_TOOLS.map((t) => (
                  <div key={t.id} className="flex items-center gap-3 px-3 py-2">
                    <code className="text-[11px] font-mono text-[var(--accent)] shrink-0" dir="ltr">{t.id}</code>
                    <span className="text-[11px] text-[var(--fg-muted)] truncate">{t.desc}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </Card>

      {/* ===== Other integrations ===== */}
      <div className="grid md:grid-cols-2 gap-4">
        <IntegrationCard
          icon={Database}
          title="Supabase"
          description="مزامنة تلقائية لكل تشغيل مكتمل — الشركات، جهات الاتصال، والتحققات إلى قاعدة دائمة."
          state={supabaseReady ? "connected" : "needs-setup"}
          stateLabel={supabaseReady ? "متصل" : "يحتاج مفاتيح"}
          actionLabel="ضبط من صفحة المفاتيح"
          onAction={() => (window.location.href = "/keys")}
        />
        <IntegrationCard
          icon={Workflow}
          title="n8n"
          description="جدولة يومية 06:00 عبر workflow جاهز: تشغيل، فحص الحالة، والتقرير."
          state={mcpOnline === false ? "needs-setup" : "ready"}
          stateLabel="workflow جاهز"
          actionLabel="نسخ رابط MCP للـClient"
          onAction={() => copy(MCP_URL, "رابط MCP")}
        />
        <IntegrationCard
          icon={Code2}
          title="REST API"
          description="كل وظائف المحرك مكشوفة REST — موثقة بالكامل مع أمثلة تفاعلية."
          state={data ? "connected" : "down"}
          stateLabel="يعمل"
          actionLabel="فتح التوثيق التفاعلي"
          onAction={() => window.open("/docs", "_blank")}
        />
        <IntegrationCard
          icon={Link2}
          title="Webhooks"
          description="إرسال أحداث المهام والـleads إلى أنظمتك لحظة حدوثها."
          state="soon"
          stateLabel="قريبًا"
          actionLabel="تفعيل"
          disabled
        />
      </div>

      {/* Usage line */}
      <div className="text-center text-[11px] text-[var(--fg-soft)]">
        إجمالي الوحدات المستهلكة عبر كل التكاملات حتى الآن: <span className="tnum font-semibold text-[var(--fg-muted)]">{formatNumber(calls)}</span>
      </div>
    </div>
  );
}

function IntegrationCard({ icon: Icon, title, description, state, stateLabel, actionLabel, onAction, disabled = false }: {
  icon: any;
  title: string;
  description: string;
  state: "connected" | "ready" | "needs-setup" | "down" | "soon";
  stateLabel: string;
  actionLabel: string;
  onAction?: () => void;
  disabled?: boolean;
}) {
  const tone =
    state === "connected" ? "success" :
    state === "ready" ? "info" :
    state === "soon" ? "default" :
    state === "down" ? "danger" : "warn";
  return (
    <Card className={cn("p-5", disabled && "opacity-75")}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex gap-3 min-w-0">
          <div className="h-9 w-9 rounded-lg bg-[var(--bg-soft)] border border-[var(--border-soft)] flex items-center justify-center text-[var(--accent)] shrink-0">
            <Icon className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <h2 className="font-semibold text-sm">{title}</h2>
            <p className="text-xs text-[var(--fg-muted)] mt-1 leading-5">{description}</p>
          </div>
        </div>
        <Badge variant={tone as any} className="text-[10px] shrink-0">
          {state === "connected" && <Check className="h-3 w-3" />}
          {stateLabel}
        </Badge>
      </div>
      <Button className="mt-4" variant="outline" size="sm" disabled={disabled} onClick={onAction}>
        {state === "soon" ? <Webhook className="h-3.5 w-3.5" /> : <ExternalLink className="h-3.5 w-3.5" />}
        {actionLabel}
      </Button>
    </Card>
  );
}
