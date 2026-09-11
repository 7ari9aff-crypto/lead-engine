import { useState } from "react";
import {
  Activity, Check, CheckCircle2, Clipboard, Code2, Database, ExternalLink,
  Globe2, Link2, Plug, RefreshCw, Webhook, Workflow, XCircle, Copy, Boxes,
  ShieldBan, Plus, Trash2,
} from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { useLiveData } from "@/hooks/useLiveData";
import { apiGet, apiPost } from "@/lib/api";
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
  const integrations = useLiveData(() => apiGet.integrations(), 10000);
  const suppression = useLiveData(() => apiGet.suppression(), 10000);
  const entitlements = useLiveData(() => apiGet.entitlements(), 15000);
  const [newEntry, setNewEntry] = useState({ channel: "email", value: "", reason: "manual" });
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

  async function connect(provider: string) {
    try {
      const { authorize_url } = await apiPost.integrationConnect(provider);
      window.location.href = authorize_url;
    } catch (e: any) {
      toast.error(e.message || "فشل بدء الربط");
    }
  }

  async function revoke(provider: string) {
    if (!confirm("فصل الاتصال وإلغاء التوكنات؟")) return;
    try {
      await apiPost.integrationRevoke(provider);
      toast.success("تم الفصل");
      integrations.refresh();
    } catch (e: any) {
      toast.error(e.message || "فشل الفصل");
    }
  }

  async function addSuppression() {
    if (!newEntry.value.trim()) return;
    try {
      await apiPost.suppressionAdd(newEntry.channel, newEntry.value.trim(), newEntry.reason);
      toast.success("تمت الإضافة لقائمة الحجب");
      setNewEntry({ ...newEntry, value: "" });
      suppression.refresh();
    } catch (e: any) {
      toast.error(e.message || "فشلت الإضافة");
    }
  }

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

      {/* ===== Platform connections (OAuth) ===== */}
      <Card className="p-5">
        <div className="flex items-center gap-2 mb-4">
          <Link2 className="h-4 w-4 text-[var(--accent)]" />
          <h2 className="text-sm font-bold">اتصالات المنصات</h2>
          <span className="text-[11px] text-[var(--fg-soft)]">اربط حساب Gmail أو CRM بحساب مؤسستك — التوكنات مشفرة ولا تُعرض أبدًا</span>
          <Button size="icon-sm" variant="ghost" className="ms-auto" onClick={() => integrations.refresh()} title="تحديث">
            <RefreshCw className={cn("h-3.5 w-3.5", integrations.loading && "animate-spin")} />
          </Button>
        </div>
        <div className="grid md:grid-cols-2 gap-3">
          {(integrations.data?.integrations ?? []).map((row) => (
            <div key={row.provider} className="flex items-center gap-3 rounded-xl border border-[var(--border)] bg-[var(--bg-soft)] p-3.5">
              <div className="h-9 w-9 rounded-lg bg-[var(--bg-elev)] border border-[var(--border-soft)] flex items-center justify-center text-[var(--accent)] shrink-0">
                <Link2 className="h-4 w-4" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-[13px] capitalize">{row.provider}</span>
                  {row.connected ? (
                    <Badge variant="success" className="text-[10px]"><CheckCircle2 className="h-3 w-3" /> متصل</Badge>
                  ) : row.configured ? (
                    <Badge variant="default" className="text-[10px]">غير متصل</Badge>
                  ) : (
                    <Badge variant="warn" className="text-[10px]">يحتاج إعداد OAuth</Badge>
                  )}
                </div>
                <div className="text-[10px] text-[var(--fg-soft)] mt-0.5 truncate" dir="ltr">
                  {row.connected ? (row.scopes || []).join(" ") : row.provider === "linkedin" ? "لا يوجد API معتمد حاليًا" : "OAuth 2.0 — موافقة عند المزود"}
                </div>
              </div>
              {row.connected ? (
                <Button size="sm" variant="outline" onClick={() => revoke(row.provider)}>فصل</Button>
              ) : (
                <Button size="sm" variant="primary" disabled={!row.configured} onClick={() => connect(row.provider)}>ربط</Button>
              )}
            </div>
          ))}
        </div>
      </Card>

      {/* ===== Suppression list ===== */}
      <Card className="p-5">
        <div className="flex items-center gap-2 mb-4">
          <ShieldBan className="h-4 w-4 text-[var(--danger)]" />
          <h2 className="text-sm font-bold">قائمة الحجب</h2>
          <span className="text-[11px] text-[var(--fg-soft)]">مين ممنوع التواصل معاه — أي إرسال مستقبلي يمر عليها إلزاميًا</span>
        </div>
        <div className="flex flex-wrap gap-2 mb-4">
          <select
            value={newEntry.channel}
            onChange={(e) => setNewEntry({ ...newEntry, channel: e.target.value })}
            className="h-9 rounded-lg border border-[var(--border)] bg-[var(--bg-soft)] px-2.5 text-[13px]"
          >
            <option value="email">إيميل</option>
            <option value="sms">SMS</option>
            <option value="whatsapp">واتساب</option>
            <option value="all">كل القنوات</option>
          </select>
          <input
            value={newEntry.value}
            onChange={(e) => setNewEntry({ ...newEntry, value: e.target.value })}
            onKeyDown={(e) => { if (e.key === "Enter") addSuppression(); }}
            placeholder="الإيميل أو الرقم"
            dir="ltr"
            className="flex-1 min-w-40 h-9 rounded-lg border border-[var(--border)] bg-[var(--bg-soft)] px-3 text-[13px] font-mono"
          />
          <select
            value={newEntry.reason}
            onChange={(e) => setNewEntry({ ...newEntry, reason: e.target.value })}
            className="h-9 rounded-lg border border-[var(--border)] bg-[var(--bg-soft)] px-2.5 text-[13px]"
          >
            <option value="manual">حظر يدوي</option>
            <option value="unsubscribed">إلغاء اشتراك</option>
            <option value="bounced">فشل توصيل</option>
            <option value="complained">شكوى</option>
            <option value="legal">قانوني</option>
          </select>
          <Button size="sm" variant="primary" onClick={addSuppression} disabled={!newEntry.value.trim()}>
            <Plus className="h-3.5 w-3.5" />
            إضافة
          </Button>
        </div>
        {(suppression.data?.entries ?? []).length === 0 ? (
          <div className="text-center py-5 text-xs text-[var(--fg-muted)]">القائمة فاضية — أضِف من النموذج أعلاه أو تلقائيًا من نتائج فحص الإيميل</div>
        ) : (
          <div className="rounded-xl border border-[var(--border)] divide-y divide-[var(--border-soft)] overflow-hidden">
            {(suppression.data?.entries ?? []).map((entry) => (
              <div key={entry.id} className="flex items-center gap-3 px-3.5 py-2">
                <XCircle className="h-3.5 w-3.5 text-[var(--danger)] shrink-0" />
                <span className="font-mono text-xs" dir="ltr">{entry.value}</span>
                <Badge variant="outline" className="text-[10px]">{entry.channel}</Badge>
                <span className="text-[10px] text-[var(--fg-soft)]">{entry.reason}</span>
                <button
                  onClick={async () => { await apiPost.suppressionRemove(entry.id); suppression.refresh(); }}
                  className="ms-auto p-1 rounded hover:bg-[var(--danger)]/15 hover:text-[var(--danger)] text-[var(--fg-soft)] transition-colors"
                  title="إزالة"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
            ))}
          </div>
        )}
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
