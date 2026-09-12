import { useEffect, useMemo, useState } from "react";
import {
  Settings, Save, RotateCcw, Check, Search, SlidersHorizontal, Timer,
  Target, Scale, Plus, X, Users, Gauge, ShieldCheck, Info,
} from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Input, Label } from "@/components/ui/Input";
import { Switch } from "@/components/ui/Switch";
import { apiGet, apiPost } from "@/lib/api";
import { friendlyError } from "@/lib/friendly";
import { toast } from "sonner";
import { Spinner } from "@/components/ui/EmptyState";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/layout/PageHeader";

type ConfigFile = { path: string; text: string; parsed: any };
type Files = Record<string, ConfigFile>;

const TABS = [
  { id: "general", label: "عام", icon: SlidersHorizontal },
  { id: "cache", label: "الاحتفاظ بالبيانات", icon: Timer },
  { id: "icp", label: "الاستهداف", icon: Target },
  { id: "legal", label: "سياسات البيانات", icon: Scale },
] as const;

// Data types kept in the cache — Arabic names instead of internal keys.
const CACHE_LABELS: Record<string, string> = {
  company_name: "اسم الشركة",
  company_domain: "نطاق الشركة",
  industry: "النشاط التجاري",
  location: "الموقع",
  employee_estimate: "عدد الموظفين التقديري",
  decision_maker: "صنّاع القرار",
  email: "البريد الإلكتروني",
  email_verification: "نتيجة فحص البريد",
  phone: "أرقام الهاتف",
  website_content: "محتوى المواقع",
  social_activity: "نشاط السوشيال",
  news_events: "الأخبار والأحداث",
  search_results: "نتائج البحث",
  apollo_people_search: "بحث Apollo للأشخاص",
  apollo_enrichment: "إثراء Apollo",
  evidence: "الأدلة والمصادر",
};

export function ConfigPage() {
  const [files, setFiles] = useState<Files>({});
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("general");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState("");

  useEffect(() => {
    apiGet
      .config()
      .then((r) => setFiles(r.files ?? {}))
      .catch((e) => toast.error(friendlyError(e)))
      .finally(() => setLoading(false));
  }, []);

  const settings = files.settings?.parsed ?? {};
  const cache = files.cache_policy?.parsed ?? {};
  const icp = files.icp_v0_saudi_dental?.parsed ?? files.icp?.parsed ?? {};
  const legal = files.legal_sa?.parsed ?? files.legal?.parsed ?? {};

  function dirtyKey(key: string, working: any): boolean {
    return JSON.stringify(working) !== JSON.stringify(files[key]?.parsed ?? {});
  }

  async function saveKey(key: string, values: Record<string, any>) {
    setSaving(true);
    try {
      await apiPost.saveConfigValues(key, values);
      setFiles((f) => ({ ...f, [key]: { ...f[key], parsed: values } }));
      toast.success("تم الحفظ وسار على النظام فورًا");
    } catch (e) {
      toast.error(friendlyError(e));
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner className="h-6 w-6 text-[var(--accent)]" />
      </div>
    );
  }

  const q = search.trim();
  const showTabs = TABS.filter((t) => !q || t.label.includes(q));

  return (
    <div className="space-y-5">
      <PageHeader
        icon={<Settings className="h-4 w-4 text-white" />}
        title="الإعدادات"
        description="اضبط سلوك المنصة من هنا — كل تغيير يعمل نسخة احتياطية تلقائيًا ويسري فورًا"
        action={
          <div className="relative">
            <Search className="absolute right-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-[var(--fg-soft)] pointer-events-none" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="ابحث في الأقسام…"
              className="h-8 w-44 rounded-lg border border-[var(--border)] bg-[var(--bg-soft)] pr-9 pl-3 text-[13px] focus:outline-none focus:border-[var(--accent)]"
            />
          </div>
        }
      />

      <div className="flex items-center gap-2 flex-wrap">
        {showTabs.map((t) => {
          const Icon = t.icon;
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={cn(
                "flex items-center gap-1.5 h-9 px-4 rounded-xl border text-[13px] font-medium transition-colors",
                tab === t.id
                  ? "bg-[var(--accent-soft)] border-[var(--accent)] text-[var(--accent-hover)]"
                  : "border-[var(--border)] hover:bg-[var(--bg-hover)]"
              )}
            >
              <Icon className="h-3.5 w-3.5" />
              {t.label}
            </button>
          );
        })}
      </div>

      {tab === "general" && (
        <GeneralTab settings={settings} dirty={dirtyKey("settings", settings)} saving={saving}
          onSave={(v) => saveKey("settings", v)} onReset={() => setFiles((f) => ({ ...f, settings: { ...f.settings } }))} />
      )}
      {tab === "cache" && (
        <CacheTab cache={cache} dirty={dirtyKey("cache_policy", cache)} saving={saving}
          onSave={(v) => saveKey("cache_policy", v)} />
      )}
      {tab === "icp" && (
        <IcpTab icp={icp} dirty={dirtyKey(files.icp_v0_saudi_dental ? "icp_v0_saudi_dental" : "icp", icp)} saving={saving}
          onSave={(v) => saveKey(files.icp_v0_saudi_dental ? "icp_v0_saudi_dental" : "icp", v)} />
      )}
      {tab === "legal" && <LegalTab legal={legal} />}
    </div>
  );
}

// ===== عام =====
function GeneralTab({ settings, dirty, saving, onSave, onReset }: {
  settings: any; dirty: boolean; saving: boolean;
  onSave: (values: any) => void; onReset: () => void;
}) {
  const router = settings.router ?? {};
  const backoff = settings.backoff ?? {};
  const job = settings.job ?? {};
  const dedup = settings.dedup ?? {};
  const verification = settings.verification ?? {};
  const scoring = settings.scoring?.weights ?? {};
  const llm = settings.llm ?? {};

  const [weights, setWeights] = useState({
    qualification: scoring.qualification ?? 0.5,
    evidence: scoring.evidence ?? 0.2,
    contact: scoring.contact ?? 0.2,
    verification: scoring.verification ?? 0.1,
  });
  const [catchAll, setCatchAll] = useState(verification.catch_all_probe ?? true);
  const weightsSum = Math.round((weights.qualification + weights.evidence + weights.contact + weights.verification) * 100);

  function collect(): any {
    return {
      ...settings,
      router: { ...router },
      backoff: { ...backoff },
      job: { ...job },
      dedup: { ...dedup },
      verification: { ...verification, catch_all_probe: catchAll },
      scoring: { ...(settings.scoring ?? {}), weights },
    };
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <span className={cn("text-[11px] flex items-center gap-1.5", weightsSum !== 100 ? "text-[var(--warn)]" : "text-[var(--fg-soft)]")}>
          {weightsSum !== 100 ? <><AlertIcon /> مجموع أوزان التقييم {weightsSum}% — المفروض 100%</> : <>الأوزان متوازنة ({weightsSum}%)</>}
        </span>
        {dirty && (
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" onClick={onReset}>
              <RotateCcw className="h-3.5 w-3.5" />
              تراجع
            </Button>
            <Button variant="primary" size="sm" loading={saving} onClick={() => onSave(collect())}>
              <Save className="h-3.5 w-3.5" />
              حفظ التغييرات
            </Button>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <Card className="p-5 space-y-4">
          <SectionTitle icon={<Gauge className="h-4 w-4" />} title="سرعة الاستجابة" desc="التعامل مع المزودين الخارجيين" />
          <NumField label="مهلة الانتظار لكل طلب" value={router.timeout_seconds ?? 30} unit="ثانية" min={5} max={120}
            onChange={(v) => { router.timeout_seconds = v; onReset(); }} />
          <NumField label="مدة التهدئة بعد توقف المزود" value={router.cooldown_default_seconds ?? 300} unit="ثانية" min={0} max={3600}
            onChange={(v) => { router.cooldown_default_seconds = v; onReset(); }} />
        </Card>

        <Card className="p-5 space-y-4">
          <SectionTitle icon={<RotateCcw className="h-4 w-4" />} title="إعادة المحاولة" desc="لو فشل طلب، ننتظر ونحاول تاني" />
          <NumField label="أول انتظار" value={backoff.base_seconds ?? 5} unit="ثانية" min={1} max={60}
            onChange={(v) => { backoff.base_seconds = v; onReset(); }} />
          <NumField label="أقصى انتظار بين المحاولات" value={backoff.max_seconds ?? 3600} unit="ثانية" min={60} max={86400}
            onChange={(v) => { backoff.max_seconds = v; onReset(); }} />
          <NumField label="انتظار التوقف المؤقت للمهام" value={Math.round((job.pause_backoff_seconds ?? 1800) / 60)} unit="دقيقة" min={1} max={1440}
            onChange={(v) => { job.pause_backoff_seconds = v * 60; onReset(); }} />
        </Card>

        <Card className="p-5 space-y-4">
          <SectionTitle icon={<Users className="h-4 w-4" />} title="دمج العملاء المكررين" desc="التحكم في تشابه البيانات قبل الدمج التلقائي" />
          <SliderField label="دمج تلقائي عند تشابه" value={Math.round((dedup.auto_merge_threshold ?? 0.95) * 100)} suffix="%"
            onChange={(v) => { dedup.auto_merge_threshold = v / 100; onReset(); }} />
          <SliderField label="عرض للمراجعة عند تشابه" value={Math.round((dedup.review_threshold ?? 0.85) * 100)} suffix="%"
            onChange={(v) => { dedup.review_threshold = v / 100; onReset(); }} />
        </Card>

        <Card className="p-5 space-y-4">
          <SectionTitle icon={<ShieldCheck className="h-4 w-4" />} title="فحص البريد" desc="التحقق من صلاحية الإيميلات قبل الاستخدام" />
          <NumField label="مهلة فحص السيرفر" value={verification.smtp_timeout ?? 10} unit="ثانية" min={3} max={60}
            onChange={(v) => { verification.smtp_timeout = v; onReset(); }} />
          <div className="flex items-center justify-between">
            <div>
              <div className="text-[13px] font-medium">فحص الدومينات المفتوحة</div>
              <div className="text-[11px] text-[var(--fg-soft)] mt-0.5">كشف الإيميلات اللي تقبل أي رسالة</div>
            </div>
            <Switch checked={catchAll} onCheckedChange={(v) => { setCatchAll(v); onReset(); }} />
          </div>
        </Card>
      </div>

      <Card className="p-5 space-y-4">
        <SectionTitle icon={<SlidersHorizontal className="h-4 w-4" />} title="أوزان تقييم العملاء" desc="أهمية كل عامل في الدرجة النهائية — المجموع المفروض 100%" />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <SliderField label="جاهزية العميل" value={Math.round(weights.qualification * 100)} suffix="%"
            onChange={(v) => { setWeights((w) => ({ ...w, qualification: v / 100 })); onReset(); }} />
          <SliderField label="قوة الأدلة والمصادر" value={Math.round(weights.evidence * 100)} suffix="%"
            onChange={(v) => { setWeights((w) => ({ ...w, evidence: v / 100 })); onReset(); }} />
          <SliderField label="سهولة التواصل" value={Math.round(weights.contact * 100)} suffix="%"
            onChange={(v) => { setWeights((w) => ({ ...w, contact: v / 100 })); onReset(); }} />
          <SliderField label="سلامة البريد" value={Math.round(weights.verification * 100)} suffix="%"
            onChange={(v) => { setWeights((w) => ({ ...w, verification: v / 100 })); onReset(); }} />
        </div>
      </Card>

      <details className="rounded-xl border border-[var(--border)] bg-[var(--bg-elev)] overflow-hidden">
        <summary className="cursor-pointer px-4 py-3 text-[13px] font-medium flex items-center gap-2 hover:bg-[var(--bg-hover)]">
          <Info className="h-4 w-4 text-[var(--fg-soft)]" />
          إعدادات الموديلات — متقدم
        </summary>
        <div className="px-5 pb-5 pt-1 grid grid-cols-1 sm:grid-cols-2 gap-4">
          <TextField label="الموديل المحلي" value={llm.local_model ?? ""} onChange={(v) => { llm.local_model = v; onReset(); }} />
          <TextField label="موديل Gemini" value={llm.cloud_models?.gemini ?? ""} onChange={(v) => { llm.cloud_models = { ...(llm.cloud_models ?? {}), gemini: v }; onReset(); }} />
          <TextField label="موديل Groq" value={llm.cloud_models?.groq ?? ""} onChange={(v) => { llm.cloud_models = { ...(llm.cloud_models ?? {}), groq: v }; onReset(); }} />
          <TextField label="موديل OpenRouter" value={llm.cloud_models?.openrouter ?? ""} onChange={(v) => { llm.cloud_models = { ...(llm.cloud_models ?? {}), openrouter: v }; onReset(); }} />
        </div>
      </details>
    </div>
  );
}

// ===== الاحتفاظ بالبيانات =====
function CacheTab({ cache, dirty, saving, onSave }: {
  cache: any; dirty: boolean; saving: boolean; onSave: (values: any) => void;
}) {
  const ttl: Record<string, number> = cache.ttl_days ?? {};
  const entries = Object.entries(ttl).filter(([k]) => CACHE_LABELS[k]);

  return (
    <div className="space-y-4">
      <Card className="p-5">
        <div className="flex items-start justify-between gap-3 flex-wrap mb-4">
          <div>
            <h3 className="text-sm font-bold">مدة الاحتفاظ بكل نوع بيانات</h3>
            <p className="text-[12px] text-[var(--fg-muted)] mt-1">
              بعد المدة دي البيانات تُجلب من جديد من مصادرها — أقصر مدة يعني بيانات أحدث، وأطول مدة توفّر في الاستهلاك.
            </p>
          </div>
          {dirty && (
            <Button variant="primary" size="sm" loading={saving} onClick={() => onSave({ ...cache })}>
              <Save className="h-3.5 w-3.5" />
              حفظ
            </Button>
          )}
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
          {entries.map(([k, days]) => (
            <div key={k} className="rounded-xl border border-[var(--border-soft)] bg-[var(--bg-soft)] p-3 flex items-center gap-3">
              <div className="flex-1 min-w-0">
                <div className="text-[13px] font-medium truncate">{CACHE_LABELS[k]}</div>
              </div>
              <input
                type="number"
                min={1}
                max={365}
                value={days}
                onChange={(e) => { ttl[k] = Math.max(1, Number(e.target.value) || 1); onSave({ ...cache }); }}
                className="w-16 h-8 rounded-lg border border-[var(--border)] bg-[var(--bg-elev)] text-center text-[13px] tnum focus:outline-none focus:border-[var(--accent)]"
              />
              <span className="text-[11px] text-[var(--fg-soft)] shrink-0">يوم</span>
            </div>
          ))}
        </div>
      </Card>
      <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-elev)] p-4 flex items-start gap-2.5">
        <Info className="h-4 w-4 text-[var(--accent)] mt-0.5 shrink-0" />
        <p className="text-[12px] text-[var(--fg-muted)]">
          الترتيب العام: بيانات الشركات الأساسية تُحفظ أطول (ثابتة نسبيًا)، وبيانات التواصل تتغير أسرع فتُحدَّث كل أسبوع، والأخبار تُجلب يوميًا.
        </p>
      </div>
    </div>
  );
}

// ===== الاستهداف =====
function ChipsField({ label, hint, items, onChange, placeholder }: {
  label: string; hint?: string; items: string[]; onChange: (items: string[]) => void; placeholder: string;
}) {
  const [draft, setDraft] = useState("");
  function add() {
    const v = draft.trim();
    if (v && !items.includes(v)) onChange([...items, v]);
    setDraft("");
  }
  return (
    <div>
      <Label>{label}</Label>
      {hint && <p className="text-[11px] text-[var(--fg-soft)] mb-1.5">{hint}</p>}
      <div className="flex flex-wrap gap-1.5 mb-2">
        {items.map((it) => (
          <Badge key={it} variant="accent" className="gap-1">
            {it}
            <button onClick={() => onChange(items.filter((x) => x !== it))} className="hover:opacity-70">
              <X className="h-3 w-3" />
            </button>
          </Badge>
        ))}
      </div>
      <div className="flex gap-2">
        <Input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder={placeholder}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }} className="h-8" />
        <Button variant="outline" size="sm" onClick={add} disabled={!draft.trim()}>
          <Plus className="h-3.5 w-3.5" />
          إضافة
        </Button>
      </div>
    </div>
  );
}

function IcpTab({ icp, dirty, saving, onSave }: {
  icp: any; dirty: boolean; saving: boolean; onSave: (values: any) => void;
}) {
  const cities: { name: string; ar: string }[] = icp.cities ?? [];
  const criteria = icp.criteria ?? {};

  return (
    <div className="space-y-4">
      <Card className="p-5 space-y-4">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <h3 className="text-sm font-bold">ملف الاستهداف الحالي</h3>
            <p className="text-[12px] text-[var(--fg-muted)] mt-1">
              {icp.name || "—"} — المنصة بتدور على العملاء المنطبقين على المعايير دي في كل مهمة توليد.
            </p>
          </div>
          {dirty && (
            <Button variant="primary" size="sm" loading={saving} onClick={() => onSave({ ...icp })}>
              <Save className="h-3.5 w-3.5" />
              حفظ
            </Button>
          )}
        </div>
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
          <div className="space-y-4">
            <ChipsField label="المدن المستهدفة" items={cities.map((c) => c.ar || c.name)}
              onChange={(items) => {
                icp.cities = items.map((ar, i) => cities[i] ? { ...cities[i], ar } : { name: ar, ar });
                onSave({ ...icp });
              }}
              placeholder="اكتب مدينة واضغط إضافة" />
            <ChipsField label="كلمات البحث بالعربي" items={icp.keywords_ar ?? []}
              onChange={(items) => { icp.keywords_ar = items; onSave({ ...icp }); }}
              placeholder="مثال: عيادة أسنان" />
            <ChipsField label="كلمات البحث بالإنجليزي" items={icp.keywords_en ?? []}
              onChange={(items) => { icp.keywords_en = items; onSave({ ...icp }); }}
              placeholder="مثال: dental clinic" />
          </div>
          <div className="space-y-4">
            <NumField label="أقل عدد فروع مؤهل" value={criteria.min_branches ?? 3} unit="فرع" min={1} max={50}
              onChange={(v) => { criteria.min_branches = v; onSave({ ...icp }); }} />
            <ChipsField label="المسميات المطلوبة لصنّاع القرار" hint="بنبني قائمة العملاء على الأشخاص بهذه المسميات" items={criteria.decision_maker_roles ?? []}
              onChange={(items) => { criteria.decision_maker_roles = items; onSave({ ...icp }); }}
              placeholder="مثال: مالك" />
          </div>
        </div>
      </Card>
      <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-elev)] p-4 flex items-start gap-2.5">
        <Info className="h-4 w-4 text-[var(--accent)] mt-0.5 shrink-0" />
        <p className="text-[12px] text-[var(--fg-muted)]">
          حدود التشغيل الحالية: {icp.v0_limits?.search_results_per_query ?? 8} نتائج لكل بحث، وحد أقصى {icp.v0_limits?.max_search_queries ?? 8} عمليات بحث في المهمة — بتتحكم في سرعة استهلاك الحصص.
        </p>
      </div>
    </div>
  );
}

// ===== سياسات البيانات =====
function LegalTab({ legal }: { legal: any }) {
  const sources: Record<string, any> = legal.source_types ?? {};
  const SOURCE_LABELS: Record<string, string> = {
    public_web: "المواقع العامة",
    search_api: "واجهات البحث",
    apollo_api: "قاعدة Apollo",
    manual_entry: "إدخال يدوي",
  };
  return (
    <div className="space-y-4">
      <Card className="p-5">
        <div className="flex items-center gap-2 mb-1">
          <ShieldCheck className="h-4 w-4 text-[var(--success)]" />
          <h3 className="text-sm font-bold">سياسة جمع البيانات — {legal.country === "SA" ? "السعودية" : "عامة"}</h3>
        </div>
        <p className="text-[12px] text-[var(--fg-muted)]">
          المنصة بتجمع وتخزن البيانات بس من المصادر المسموح بيها صراحةً — أي مصدر مش معرّف هنا محجوب تلقائيًا.
        </p>
        <div className="mt-4 space-y-2">
          {Object.entries(sources).map(([k, v]) => (
            <div key={k} className="flex items-center justify-between gap-3 rounded-xl border border-[var(--border-soft)] bg-[var(--bg-soft)] px-4 py-2.5">
              <span className="text-[13px] font-medium">{SOURCE_LABELS[k] ?? k}</span>
              <div className="flex items-center gap-2 flex-wrap justify-end">
                {v.approved ? (
                  <Badge variant="success" className="text-[10px]"><Check className="h-3 w-3" /> مسموح</Badge>
                ) : (
                  <Badge variant="danger" className="text-[10px]"><X className="h-3 w-3" /> محجوب</Badge>
                )}
                <span className="text-[11px] text-[var(--fg-soft)]">
                  مدة الاحتفاظ: {legal.default_retention_days ?? v.retention_days ?? 30} يوم
                </span>
              </div>
            </div>
          ))}
        </div>
      </Card>
      <div className="rounded-xl border border-[var(--warn)]/40 bg-[var(--warn)]/5 p-4 flex items-start gap-2.5">
        <AlertIcon />
        <p className="text-[12px] text-[var(--fg-muted)]">
          السياسات دي محرك حماية داخل المنصة ومش استشارة قانونية — راجع دائمًا لوائح حماية البيانات المحلية قبل التوسع في سوق جديد.
        </p>
      </div>
    </div>
  );
}

// ===== Shared small pieces =====
function SectionTitle({ icon, title, desc }: { icon: React.ReactNode; title: string; desc: string }) {
  return (
    <div className="flex items-start gap-2.5">
      <span className="text-[var(--accent)] mt-0.5">{icon}</span>
      <div>
        <div className="text-[13px] font-bold">{title}</div>
        <div className="text-[11px] text-[var(--fg-soft)] mt-0.5">{desc}</div>
      </div>
    </div>
  );
}

function NumField({ label, value, unit, min, max, onChange }: {
  label: string; value: number; unit: string; min: number; max: number; onChange: (v: number) => void;
}) {
  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 min-w-0">
        <div className="text-[13px] font-medium">{label}</div>
      </div>
      <input
        type="number" min={min} max={max} value={value}
        onChange={(e) => onChange(Math.min(max, Math.max(min, Number(e.target.value) || min)))}
        className="w-20 h-8 rounded-lg border border-[var(--border)] bg-[var(--bg-soft)] text-center text-[13px] tnum focus:outline-none focus:border-[var(--accent)]"
      />
      <span className="text-[11px] text-[var(--fg-soft)] w-10 shrink-0">{unit}</span>
    </div>
  );
}

function SliderField({ label, value, suffix, onChange }: {
  label: string; value: number; suffix: string; onChange: (v: number) => void;
}) {
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[13px] font-medium">{label}</span>
        <span className="tnum text-[13px] font-bold text-[var(--accent)]">{value}{suffix}</span>
      </div>
      <input
        type="range" min={0} max={100} value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-[var(--accent)]"
      />
    </div>
  );
}

function TextField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);
  return (
    <div>
      <Label>{label}</Label>
      <Input value={draft} onChange={(e) => setDraft(e.target.value)} onBlur={() => onChange(draft.trim())}
        dir="ltr" className="font-mono text-xs h-8" />
    </div>
  );
}

function AlertIcon() {
  return <Info className="h-3.5 w-3.5 inline shrink-0" />;
}
