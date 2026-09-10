import { useState } from "react";
import {
  Activity,
  Check,
  CheckCircle2,
  Clipboard,
  Code2,
  Database,
  ExternalLink,
  Globe2,
  Link2,
  Plug,
  RefreshCw,
  Server,
  Webhook,
  XCircle,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { useLiveData } from "@/hooks/useLiveData";
import { apiGet } from "@/lib/api";
import { toast } from "sonner";
import { cn, formatNumber } from "@/lib/utils";
import { PageHeader } from "@/components/layout/PageHeader";

const BACKEND_BASE = (import.meta.env.VITE_BACKEND_URL || window.location.origin).replace(/\/$/, "");
const MCP_URL = `${BACKEND_BASE}/mcp`;

export function IntegrationsPage() {
  const { data, loading, refresh } = useLiveData(() => apiGet.status(), 10000);
  const [testing, setTesting] = useState(false);
  const [mcpOnline, setMcpOnline] = useState<boolean | null>(null);

  const providers = data?.providers ?? [];
  const configured = providers.filter((provider) => provider.has_key || provider.is_local).length;
  const calls = providers.reduce((sum, provider) => sum + (provider.calls || 0), 0);
  const supabaseReady = Boolean(data?.system.supabase_configured);

  async function copy(text: string, label: string) {
    await navigator.clipboard.writeText(text);
    toast.success(`تم نسخ ${label}`);
  }

  async function testMcp() {
    setTesting(true);
    try {
      const response = await fetch(MCP_URL, { headers: { Accept: "application/json" } });
      setMcpOnline(response.ok);
      toast[response.ok ? "success" : "error"](response.ok ? "خادم MCP متصل" : "خادم MCP غير متاح");
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
        icon={<Plug className="h-4 w-4 text-[var(--accent)]" />}
        title="التكاملات و MCP"
        description="اربط محرك الـLeads بالأدوات الخارجية وتابع حالة كل قناة من مكان واحد."
        action={
          <Button variant="outline" onClick={refresh} disabled={loading}>
            <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} /> تحديث الحالة
          </Button>
        }
      />

      <section className="grid grid-cols-2 xl:grid-cols-4 gap-3">
        <Metric icon={Plug} label="تكاملات جاهزة" value="1" detail="MCP متاح الآن" />
        <Metric icon={Server} label="المزوّدون" value={formatNumber(configured)} detail={`من ${formatNumber(providers.length)} مسجل`} />
        <Metric icon={Activity} label="الاستدعاءات" value={formatNumber(calls)} detail="إجمالي الاستخدام" />
        <Metric icon={Database} label="قاعدة البيانات" value={supabaseReady ? "متصلة" : "غير مهيأة"} detail="Supabase" tone={supabaseReady ? "success" : "warn"} />
      </section>

      <Card className="border-[var(--accent)]/30 overflow-hidden">
        <div className="h-1 bg-[var(--accent)]" />
        <CardHeader className="pb-4">
          <div className="flex items-start gap-3">
            <div className="h-10 w-10 rounded-lg bg-[var(--accent-soft)] text-[var(--accent)] flex items-center justify-center">
              <Webhook className="h-5 w-5" />
            </div>
            <div>
              <CardTitle>MCP Server</CardTitle>
              <CardDescription>شغّل أدوات توليد الـleads من Claude أو Cursor أو n8n.</CardDescription>
            </div>
          </div>
          <Badge variant={mcpOnline === false ? "danger" : "success"}>
            {mcpOnline === false ? <XCircle className="h-3.5 w-3.5" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
            {mcpOnline === false ? "غير متصل" : "جاهز"}
          </Badge>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="grid md:grid-cols-[1fr_auto] gap-3 items-end">
            <div>
              <label className="text-xs font-semibold text-[var(--fg-muted)] block mb-1.5">رابط MCP</label>
              <div className="flex items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--bg-soft)] px-3 h-10" dir="ltr">
                <Globe2 className="h-4 w-4 text-[var(--fg-soft)] shrink-0" />
                <code className="text-xs truncate">{MCP_URL}</code>
              </div>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => copy(MCP_URL, "الرابط")} title="نسخ الرابط">
                <Clipboard className="h-4 w-4" /> نسخ الرابط
              </Button>
              <Button variant="primary" onClick={testMcp} loading={testing}>
                <Activity className="h-4 w-4" /> اختبار الاتصال
              </Button>
            </div>
          </div>

          <div className="grid md:grid-cols-3 gap-3">
            <IntegrationAction icon={Code2} title="Claude / Cursor" description="إعداد JSON جاهز" onClick={() => copy(mcpConfig, "إعداد MCP")} />
            <IntegrationAction icon={Webhook} title="n8n" description="استخدم MCP Client" onClick={() => copy(MCP_URL, "رابط n8n")} />
            <IntegrationAction icon={Link2} title="API مباشر" description="JSON-RPC عبر HTTP" onClick={() => copy("POST " + MCP_URL, "عنوان API")} />
          </div>

          <div className="rounded-lg border border-[var(--border-soft)] bg-[var(--bg-soft)] p-3">
            <div className="flex items-center justify-between gap-3 mb-2">
              <span className="text-xs font-semibold">الأدوات المتاحة</span>
              <Badge variant="outline">5 أدوات</Badge>
            </div>
            <div className="flex flex-wrap gap-2" dir="ltr">
              {['run_lead_generation', 'get_job_status', 'list_leads', 'verify_email', 'system_status'].map((tool) => (
                <code key={tool} className="text-[11px]">{tool}</code>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      <section className="grid lg:grid-cols-2 gap-4">
        <IntegrationCard icon={Database} title="Supabase" description="مزامنة الـleads والنتائج إلى قاعدة بيانات دائمة." connected={supabaseReady} action="إدارة من الإعدادات" />
        <IntegrationCard icon={Webhook} title="Webhooks" description="الخطوة التالية: إرسال أحداث المهام والـleads إلى أنظمتك." connected={false} action="قريبًا" disabled />
        <IntegrationCard icon={ExternalLink} title="n8n" description="شغّل الـpipeline من workflow خارجي عبر MCP." connected={false} action="نسخ رابط MCP" onAction={() => copy(MCP_URL, "رابط MCP")} />
        <IntegrationCard icon={Server} title="Backend API" description="حالة الـAPI الحالية وبيانات الخدمة." connected={Boolean(data)} action="فتح OpenAPI" onAction={() => window.open("/openapi.json", "_blank")} />
      </section>
    </div>
  );
}

function Metric({ icon: Icon, label, value, detail, tone = "accent" }: { icon: typeof Plug; label: string; value: string; detail: string; tone?: "accent" | "success" | "warn" }) {
  return (
    <Card className="shadow-none">
      <CardContent className="p-4">
        <div className="flex items-center justify-between gap-2 mb-3">
          <span className="text-xs text-[var(--fg-muted)]">{label}</span>
          <Icon className={cn("h-4 w-4", tone === "success" ? "text-[var(--success)]" : tone === "warn" ? "text-[var(--warn)]" : "text-[var(--accent)]")} />
        </div>
        <div className="text-xl font-bold tabular-nums">{value}</div>
        <div className="text-[11px] text-[var(--fg-soft)] mt-1">{detail}</div>
      </CardContent>
    </Card>
  );
}

function IntegrationAction({ icon: Icon, title, description, onClick }: { icon: typeof Code2; title: string; description: string; onClick: () => void }) {
  return (
    <button onClick={onClick} className="text-right rounded-lg border border-[var(--border-soft)] bg-[var(--bg-soft)] p-3 hover:border-[var(--accent)] hover:bg-[var(--bg-hover)] transition-colors">
      <Icon className="h-4 w-4 text-[var(--accent)] mb-2" />
      <div className="text-sm font-semibold">{title}</div>
      <div className="text-xs text-[var(--fg-muted)] mt-1">{description}</div>
    </button>
  );
}

function IntegrationCard({ icon: Icon, title, description, connected, action, onAction, disabled = false }: { icon: typeof Database; title: string; description: string; connected: boolean; action: string; onAction?: () => void; disabled?: boolean }) {
  return (
    <Card className={cn("shadow-none", disabled && "opacity-70")}>
      <CardContent className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="flex gap-3">
            <div className="h-9 w-9 rounded-lg bg-[var(--bg-soft)] flex items-center justify-center text-[var(--accent)]"><Icon className="h-4 w-4" /></div>
            <div>
              <h2 className="font-semibold text-sm">{title}</h2>
              <p className="text-xs text-[var(--fg-muted)] mt-1 max-w-sm">{description}</p>
            </div>
          </div>
          <Badge variant={connected ? "success" : disabled ? "default" : "warn"}>
            {connected ? <Check className="h-3 w-3" /> : <Activity className="h-3 w-3" />}
            {connected ? "متصل" : disabled ? "قريبًا" : "يحتاج إعداد"}
          </Badge>
        </div>
        <Button className="mt-4" variant="outline" size="sm" disabled={disabled} onClick={onAction}>{action}</Button>
      </CardContent>
    </Card>
  );
}
