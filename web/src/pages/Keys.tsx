import { useMemo, useState } from "react";
import {
  KeyRound, Cpu, Search, Database, Mail, HardDrive, Server, RefreshCw,
  ExternalLink, ChevronDown, Check, Save, RotateCcw, Coins, Zap, Hash,
  Plus, X, Eye, EyeOff,
} from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Input } from "@/components/ui/Input";
import { Switch } from "@/components/ui/Switch";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageSkeleton } from "@/components/ui/Skeleton";
import { useLiveData } from "@/hooks/useLiveData";
import { apiGet, apiPost, type KeyUsageResponse, type ProviderUsageRow, type StatusResponse } from "@/lib/api";
import { toast } from "sonner";
import { friendlyError, TASK_LABELS } from "@/lib/friendly";
import { cn } from "@/lib/utils";

const DISPLAY: Record<string, string> = {
  gemini: "Gemini", groq: "Groq", openrouter: "OpenRouter", ollama: "Ollama",
  tavily: "Tavily", brave: "Brave Search", exa: "Exa", apollo: "Apollo.io",
  hunter: "Hunter.io", abstract: "AbstractAPI", supabase: "Supabase",
};

const GROUPS: { id: string; title: string; icon: any; desc: string }[] = [
  { id: "llm", title: "النماذج اللغوية", icon: Cpu, desc: "التأهيل والاستدلال — الأولوية: Gemini ثم Groq ثم OpenRouter ثم Ollama" },
  { id: "search", title: "البحث", icon: Search, desc: "الاكتشاف — الأولوية: Tavily ثم Brave ثم Exa" },
  { id: "data", title: "بيانات الشركات والأشخاص", icon: Database, desc: "الإثراء الانتقائي بميزانية محسوبة" },
  { id: "email", title: "البريد", icon: Mail, desc: "إيجاد وفحص الإيميلات بخمس حالات" },
  { id: "storage", title: "التخزين والمحلي", icon: HardDrive, desc: "قاعدة الـleads والمسار المحلي" },
];

const TYPE_OF: Record<string, string> = {
  gemini: "llm", groq: "llm", openrouter: "llm",
  tavily: "search", brave: "search", exa: "search",
  apollo: "data", hunter: "email", abstract: "email",
};

function fmt(n: number | null | undefined): string {
  if (n == null) return "0";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1).replace(/\.0$/, "") + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1).replace(/\.0$/, "") + "k";
  return String(Math.round(n));
}

export function KeysPage() {
  const usage = useLiveData<KeyUsageResponse>(() => apiGet.keysUsage(), 10000);
  const keys = useLiveData(() => apiGet.keys(), 30000);
  const status = useLiveData<StatusResponse>(() => apiGet.status(), 8000);

  const loading = usage.loading || keys.loading || status.loading;

  if (loading && !usage.data) return <PageSkeleton />;

  const providerRows = usage.data?.providers ?? [];
  const totals = usage.data?.totals;
  const keyRows = keys.data?.keys ?? [];

  const activeKeys = providerRows.reduce((n, p) => n + p.keys_configured, 0);
  const availableProviders = providerRows.filter((p) => p.status === "active" && p.keys_configured > 0).length;
  const quotaPercents = providerRows.map((p) => p.live?.percent ?? p.quota.percent).filter((x): x is number => x != null);
  const maxQuota = quotaPercents.length ? Math.max(...quotaPercents) : null;
  const totalTokens = (totals?.prompt_tokens ?? 0) + (totals?.completion_tokens ?? 0);

  const supabaseKeys = keyRows.filter((k) => k.group === "storage");
  const localKeys = keyRows.filter((k) => k.group === "local");
  const apiProviderGroups: Record<string, ProviderUsageRow[]> = {
    llm: providerRows.filter((p) => TYPE_OF[p.provider] === "llm"),
    search: providerRows.filter((p) => TYPE_OF[p.provider] === "search"),
    data: providerRows.filter((p) => TYPE_OF[p.provider] === "data"),
    email: providerRows.filter((p) => TYPE_OF[p.provider] === "email"),
  };

  function refreshAll() {
    usage.refresh();
    keys.refresh();
    status.refresh();
  }

  return (
    <div className="space-y-6">
      <PageHeader
        icon={<KeyRound className="h-4 w-4 text-white" />}
        title="المفاتيح والمزودون"
        description="كل مفاتيحك في مكان واحد — الاستهلاك والتوكنز لكل مفتاح، وضبط سلوك كل مزوّد"
        action={
          <Button variant="outline" size="sm" onClick={refreshAll}>
            <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
            تحديث
          </Button>
        }
      />

      {/* Summary strip */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatChip icon={<KeyRound className="h-4 w-4" />} label="مفاتيح مفعّلة" value={String(activeKeys)} hint="عبر كل المزودين" />
        <StatChip icon={<Zap className="h-4 w-4" />} label="مزودون جاهزون" value={`${availableProviders}/${providerRows.length}`} hint="لهم مفتاح وحالة نشطة" />
        <StatChip icon={<Coins className="h-4 w-4" />} label="أعلى استهلاك حصة" value={maxQuota != null ? `${maxQuota}%` : "—"} hint="من الحد المُعد للمزود" tone={maxQuota != null && maxQuota >= 85 ? "warn" : undefined} />
        <StatChip icon={<Hash className="h-4 w-4" />} label="إجمالي التوكنز" value={fmt(totalTokens)} hint={`${fmt(totals?.prompt_tokens ?? 0)} إدخال · ${fmt(totals?.completion_tokens ?? 0)} إخراج`} />
      </div>

      {/* Provider groups */}
      {GROUPS.map((group) => {
        const GroupIcon = group.icon;
        const cards = apiProviderGroups[group.id] ?? [];
        const extras = group.id === "storage" ? [...supabaseKeys, ...localKeys] : [];
        if (!cards.length && !extras.length) return null;
        return (
          <section key={group.id} className="space-y-3">
            <div className="flex items-baseline gap-2.5 flex-wrap">
              <GroupIcon className="h-4 w-4 text-[var(--accent)] shrink-0" />
              <h2 className="text-sm font-bold">{group.title}</h2>
              <span className="text-[11px] text-[var(--fg-soft)]">{group.desc}</span>
            </div>
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
              {cards.map((p) => (
                <ProviderCard
                  key={p.provider}
                  row={p}
                  statusRows={(status.data?.providers ?? []).filter((r) => r.name === p.provider)}
                  onChanged={refreshAll}
                />
              ))}
              {extras.map((k) => (
                <PlainKeyCard key={k.name} field={k} onChanged={keys.refresh} />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}

function StatChip({ icon, label, value, hint, tone }: {
  icon: React.ReactNode; label: string; value: string; hint?: string; tone?: "warn";
}) {
  return (
    <Card className="p-3.5 flex items-start gap-3">
      <div className={cn(
        "h-8 w-8 rounded-lg flex items-center justify-center shrink-0",
        tone === "warn" ? "bg-[var(--warn)]/12 text-[var(--warn)]" : "bg-[var(--accent-soft)] text-[var(--accent)]"
      )}>
        {icon}
      </div>
      <div className="min-w-0">
        <div className="text-lg font-bold tnum leading-none">{value}</div>
        <div className="text-[11px] font-medium text-[var(--fg-muted)] mt-1">{label}</div>
        {hint && <div className="text-[10px] text-[var(--fg-soft)] mt-0.5 truncate">{hint}</div>}
      </div>
    </Card>
  );
}

// ===== Main provider card =====
function ProviderCard({ row, statusRows, onChanged }: {
  row: ProviderUsageRow;
  statusRows: StatusResponse["providers"];
  onChanged: () => void;
}) {
  const [value, setValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [expanded, setExpanded] = useState(false);

  const main = statusRows[0];
  const enabled = main ? main.status !== "disabled" : true;
  const hasKeys = row.keys_configured > 0;
  const percent = row.live?.percent ?? row.quota.percent;
  const liveFromProvider = row.live?.percent != null;
  const needsKey = row.provider !== "ollama";

  async function save() {
    setSaving(true);
    try {
      await apiPost.saveKeys({ [row.env_key]: value.trim() });
      toast.success(hasKeys ? "تم تحديث المفاتيح وتفعيلها فورًا" : "تم حفظ المفتاح وتفعيله فورًا");
      setValue("");
      onChanged();
    } catch (e: any) {
      toast.error(friendlyError(e));
    } finally {
      setSaving(false);
    }
  }

  async function clearKeys() {
    if (!confirm("إزالة كل مفاتيح هذا المزود؟")) return;
    setSaving(true);
    try {
      await apiPost.saveKeys({ [row.env_key]: "" });
      toast.success("تمت إزالة المفاتيح");
      onChanged();
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card className={cn("p-4 space-y-3.5", needsKey && !hasKeys && "border-dashed")}>
      {/* Header */}
      <div className="flex items-center gap-2.5">
        <span className={cn("h-2 w-2 rounded-full shrink-0",
          needsKey && !hasKeys ? "bg-[var(--fg-soft)]" :
          row.status === "active" ? "bg-[var(--success)]" : "bg-[var(--warn)]")}
          title={row.status ?? ""} />
        <span className="font-bold text-sm">{DISPLAY[row.provider] ?? row.provider}</span>
        {row.provider === "ollama" && <Badge variant="default" className="text-[10px]">محلي — بدون مفتاح</Badge>}
        {row.keys_configured > 1 && (
          <Badge variant="accent" className="text-[10px] tnum">{row.keys_configured} مفاتيح بتدوير تلقائي</Badge>
        )}
        <a href={row.docs_url} target="_blank" rel="noreferrer" className="ms-auto text-[var(--fg-soft)] hover:text-[var(--accent)] transition-colors" title="إدارة المفاتيح عند المزود">
          <ExternalLink className="h-3.5 w-3.5" />
        </a>
      </div>

      {/* Quota bar */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between text-[11px]">
          <span className="text-[var(--fg-muted)]">
            {row.quota.limit != null ? (
              <>الحصة: <span className="tnum font-semibold text-[var(--fg)]">{fmt(row.quota.used)}</span> من <span className="tnum">{fmt(row.quota.limit)}</span> {row.quota.kind === "credits" ? "كريدت" : row.quota.kind === "usd" ? "دولار" : ""}</>
            ) : row.provider === "ollama" ? "غير محدودة — تشغيل محلي" : "الحد غير محدد — التتبع من السجل المحلي"}
          </span>
          {percent != null && (
            <span className={cn("tnum font-bold",
              percent >= 85 ? "text-[var(--danger)]" : percent >= 60 ? "text-[var(--warn)]" : "text-[var(--success)]")}>
              {percent}%
            </span>
          )}
        </div>
        {percent != null && (
          <div className="h-1.5 rounded-full bg-[var(--bg-soft)] overflow-hidden">
            <div
              className={cn("h-full rounded-full transition-all",
                percent >= 85 ? "bg-[var(--danger)]" : percent >= 60 ? "bg-[var(--warn)]" : "bg-[var(--success)]")}
              style={{ width: `${Math.min(100, percent)}%` }}
            />
          </div>
        )}
        {liveFromProvider && (
          <div className="text-[10px] text-[var(--success)]">النسبة مباشرة من المزود نفسه</div>
        )}
      </div>

      {/* Usage stats */}
      <div className="grid grid-cols-3 gap-2 text-center">
        <UsageMini icon={<Hash className="h-3 w-3" />} value={fmt(row.usage.total_tokens)} label="توكن" />
        <UsageMini icon={<Zap className="h-3 w-3" />} value={fmt(row.usage.units)} label="وحدة" />
        <UsageMini icon={<RefreshCw className="h-3 w-3" />} value={fmt(row.usage.calls)} label="استدعاء" />
      </div>

      {/* Per-key breakdown (only when multiple keys) */}
      {row.keys.length > 1 && (
        <div className="rounded-lg border border-[var(--border-soft)] overflow-hidden">
          {row.keys.map((k, i) => (
            <div key={i} className="flex items-center gap-2 px-3 py-1.5 text-[11px] odd:bg-[var(--bg-soft)]">
              <span className="font-mono text-[var(--fg-muted)]" dir="ltr">{k.masked}</span>
              <span className="ms-auto tnum text-[var(--fg-muted)]">{fmt(k.prompt_tokens)}+{fmt(k.completion_tokens)} توكن</span>
              <span className="tnum text-[var(--fg-soft)]">{k.calls} استدعاء</span>
            </div>
          ))}
        </div>
      )}

      {/* Key input */}
      {needsKey && (
        <div className="flex gap-2">
          <Input
            type="password"
            dir="ltr"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={hasKeys ? "استبدل المفاتيح — مفتاح لكل سطر" : "الصق المفتاح — أو عدة مفاتيح كل سطر"}
            className="font-mono text-xs"
            onKeyDown={(e) => { if (e.key === "Enter" && value.trim()) save(); }}
          />
          <Button variant="primary" size="sm" disabled={!value.trim()} loading={saving} onClick={save} className="shrink-0">
            <Check className="h-3.5 w-3.5" />
            حفظ
          </Button>
          {hasKeys && (
            <Button variant="ghost" size="icon-sm" onClick={clearKeys} title="إزالة المفاتيح" className="shrink-0 text-[var(--danger)]">
              <X className="h-3.5 w-3.5" />
            </Button>
          )}
        </div>
      )}

      {/* Provider settings (merged from the old Providers page) */}
      {statusRows.length > 0 && (
        <div className="border-t border-[var(--border-soft)] pt-2">
          <button
            onClick={() => setExpanded(!expanded)}
            className="w-full flex items-center gap-1.5 text-[11px] text-[var(--fg-muted)] hover:text-[var(--fg)] transition-colors"
          >
            <ChevronDown className={cn("h-3 w-3 transition-transform", expanded && "rotate-180")} />
            إعدادات المزود — التفعيل والنموذج والرابط
          </button>
          {expanded && (
            <div className="mt-2.5 space-y-2.5 animate-fade-in">
              <div className="flex items-center justify-between">
                <span className="text-xs text-[var(--fg-muted)]">مفعّل في الروتر</span>
                <Switch
                  checked={enabled}
                  onCheckedChange={async (checked) => {
                    await apiPost.providerSetStatus(main.name, main.task, checked ? "active" : "disabled");
                    toast.success(checked ? "تم التفعيل" : "تم التعطيل — الروتر سيتخطاه");
                    onChanged();
                  }}
                />
              </div>
              <div className="space-y-1.5">
                <Input
                  dir="ltr"
                  defaultValue={main.base_url ?? ""}
                  placeholder="رابط خاص للمزود — متقدم (اختياري)"
                  className="font-mono text-xs h-8"
                  id={`base-${row.provider}`}
                />
                <Input
                  dir="ltr"
                  defaultValue={main.model_name ?? ""}
                  placeholder="اسم الموديل (اختياري)"
                  className="font-mono text-xs h-8"
                  id={`model-${row.provider}`}
                />
                <div className="flex gap-2">
                  <Button
                    size="sm" variant="outline"
                    onClick={async () => {
                      const base = (document.getElementById(`base-${row.provider}`) as HTMLInputElement)?.value ?? "";
                      const model = (document.getElementById(`model-${row.provider}`) as HTMLInputElement)?.value ?? "";
                      await apiPost.providerConfig(main.name, main.task, { base_url: base, model_name: model });
                      toast.success("تم حفظ إعدادات المزود");
                      onChanged();
                    }}
                  >
                    <Save className="h-3 w-3" /> حفظ الإعدادات
                  </Button>
                  <Button
                    size="sm" variant="ghost"
                    onClick={async () => {
                      await apiPost.providerReset(main.name, main.task);
                      toast.success("تم تصفير الاستهلاك والحالة");
                      onChanged();
                    }}
                  >
                    <RotateCcw className="h-3 w-3" /> تصفير الحصة
                  </Button>
                </div>
              </div>
              {statusRows.length > 1 && (
                <div className="text-[10px] text-[var(--fg-soft)]">
                  يُستخدم أيضًا في: {statusRows.slice(1).map((r) => TASK_LABELS[r.task] ?? r.task).join(" · ")} — بنفس المفتاح
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

function UsageMini({ icon, value, label }: { icon: React.ReactNode; value: string; label: string }) {
  return (
    <div className="rounded-lg bg-[var(--bg-soft)] border border-[var(--border-soft)] py-1.5 px-2">
      <div className="text-[13px] font-bold tnum flex items-center justify-center gap-1">
        <span className="text-[var(--fg-soft)]">{icon}</span>
        {value}
      </div>
      <div className="text-[10px] text-[var(--fg-soft)]">{label}</div>
    </div>
  );
}

// ===== Plain key card (Supabase / Ollama) =====
function PlainKeyCard({ field, onChanged }: {
  field: { name: string; group: string; configured: boolean; masked: string; plain?: boolean };
  onChanged: () => void;
}) {
  const [value, setValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [show, setShow] = useState(false);
  const isOllama = field.group === "local";
  const title = field.name === "SUPABASE_URL" ? "Supabase — رابط المشروع"
    : field.name === "SUPABASE_SERVICE_KEY" ? "Supabase — مفتاح الخدمة"
    : "Ollama — عنوان السيرفر المحلي";

  async function save() {
    setSaving(true);
    try {
      await apiPost.saveKeys({ [field.name]: value.trim() });
      toast.success("تم الحفظ والتفعيل");
      setValue("");
      onChanged();
    } catch (e: any) {
      toast.error(friendlyError(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card className="p-4 space-y-3">
      <div className="flex items-center gap-2.5">
        {isOllama ? <Server className="h-4 w-4 text-[var(--accent)]" /> : <HardDrive className="h-4 w-4 text-[var(--accent)]" />}
        <span className="font-bold text-sm">{title}</span>
        {field.configured ? (
          <Badge variant="success" className="text-[10px]">مضبوط</Badge>
        ) : (
          <Badge variant="default" className="text-[10px]">غير مضبوط</Badge>
        )}
      </div>
      {field.configured && field.masked && (
        <div className="text-[11px] text-[var(--fg-muted)] font-mono" dir="ltr">{field.masked}</div>
      )}
      <div className="flex gap-2">
        <Input
          type={show || field.plain ? "text" : "password"}
          dir="ltr"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={isOllama ? "http://localhost:11434" : field.plain ? "https://xxxx.supabase.co" : "الصق المفتاح"}
          className="font-mono text-xs"
          onKeyDown={(e) => { if (e.key === "Enter" && value.trim()) save(); }}
        />
        {!field.plain && (
          <Button variant="ghost" size="icon-sm" onClick={() => setShow(!show)} className="shrink-0" title={show ? "إخفاء" : "إظهار"}>
            {show ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
          </Button>
        )}
        <Button variant="primary" size="sm" disabled={!value.trim()} loading={saving} onClick={save} className="shrink-0">
          <Plus className="h-3.5 w-3.5" />
          حفظ
        </Button>
      </div>
    </Card>
  );
}
