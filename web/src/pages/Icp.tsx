/**
 * ICP criteria — stage 2 gate as a first-class page: versioned criteria the
 * operator controls. The ACTIVE version drives search planning, deterministic
 * gates, and re-qualification.
 */
import { useState, useEffect, useMemo } from "react";
import {
  Loader2,
  CheckCircle2,
  History,
  Save,
  SlidersHorizontal,
  Sparkles,
  MapPin,
  Tag,
  ShieldAlert,
  FileCode,
  Check,
  X,
  RotateCcw,
  Building2,
  Plus,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Input } from "@/components/ui/Input";
import { useLiveData } from "@/hooks/useLiveData";
import { apiGetExtra, apiPostExtra, type IcpVersion } from "@/lib/api";
import { friendlyError } from "@/lib/friendly";
import { PageHeader } from "@/components/layout/PageHeader";
import { Spinner } from "@/components/ui/EmptyState";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

// Industry Presets — globally applicable across any market
const PRESETS = [
  {
    id: "saas",
    label: "شركات البرمجيات والـSaaS",
    icon: "💻",
    industry: "saas",
    keywords_ar: ["شركة برمجيات", "حلول سحابية", "أنظمة SaaS", "تقنية معلومات"],
    keywords_en: ["saas company", "software development", "cloud solutions", "b2b software"],
    negative_keywords: ["دليل", "وظائف", "تدريب", "تحميل مجاني"],
    decision_makers: ["CEO", "Founder", "CTO", "Head of Sales", "الرئيس التنفيذي", "مؤسس"],
    notes: "شركات برمجيات ومنتجات رقمية B2B مستقلة",
  },
  {
    id: "marketing",
    label: "وكالات التسويق الرقمي",
    icon: "📈",
    industry: "marketing",
    keywords_ar: ["وكالة تسويق", "تسويق رقمي", "دعاية وإعلان", "إدارة حملات"],
    keywords_en: ["marketing agency", "digital advertising", "performance marketing", "media agency"],
    negative_keywords: ["وظائف", "دليل", "مستقلين"],
    decision_makers: ["Managing Director", "Founder", "CEO", "المدير العام", "مؤسس"],
    notes: "وكالات تسويق رقمي وإعلانات B2B نشطة",
  },
  {
    id: "realestate",
    label: "المقاولات والتطوير العقاري",
    icon: "🏗️",
    industry: "contracting",
    keywords_ar: ["شركة مقاولات", "تطوير عقاري", "تشطيب وديكور", "استشارات هندسية"],
    keywords_en: ["contracting company", "real estate development", "interior design", "construction"],
    negative_keywords: ["وسيط فردي", "شقق للإيجار", "وظائف"],
    decision_makers: ["ceo", "general manager", "الرئيس التنفيذي", "المدير العام", "مهندس"],
    notes: "شركات مقاولات وتطوير عقاري معتمدة",
  },
  {
    id: "accounting",
    label: "المحاسبة والاستشارات المالية",
    icon: "🏢",
    industry: "accounting",
    keywords_ar: ["مكتب محاسبة", "مراجعة حسابات", "مستشار ضريبي", "استشارات مالية"],
    keywords_en: ["accounting firm", "auditing", "tax consultant", "financial advisor"],
    negative_keywords: ["برنامج محاسبة", "تحميل", "وظائف", "دورات تدريبية"],
    decision_makers: ["partner", "certified accountant", "محاسب قانوني", "شريك", "المدير"],
    notes: "مكاتب مراجعة ومحاسبة معتمدة",
  },
  {
    id: "healthcare",
    label: "المراكز والعيادات الطبية",
    icon: "🏥",
    industry: "healthcare",
    keywords_ar: ["مجمع طبي", "مركز رعاية", "مستشفى تخصصي", "مركز عيادات"],
    keywords_en: ["medical center", "healthcare clinic", "specialized clinic"],
    negative_keywords: ["دليل", "وظائف", "مستشفى حكومي"],
    decision_makers: ["owner", "medical director", "المدير الطبي", "المدير التنفيذي"],
    notes: "مجمعات ومراكز طبية خاصة",
  },
];

// Suggested global locations — user can add any city freely
const SUGGESTED_LOCATIONS = [
  { name: "Dubai", ar: "دبي" },
  { name: "Riyadh", ar: "الرياض" },
  { name: "Cairo", ar: "القاهرة" },
  { name: "London", ar: "لندن" },
  { name: "New York", ar: "نيويورك" },
  { name: "Istanbul", ar: "إسطنبول" },
  { name: "Berlin", ar: "برلين" },
  { name: "Singapore", ar: "سنغافورة" },
];

export function IcpPage() {
  const { data, loading, refresh } = useLiveData(() => apiGetExtra.icps("agentic"), 15000);
  const versions = data?.versions || [];
  const active = data?.active;

  // View mode: Visual Builder vs JSON Code
  const [mode, setMode] = useState<"visual" | "json">("visual");

  // Form states for Visual Builder
  const [selectedPresetId, setSelectedPresetId] = useState<string>("saas");
  const [industry, setIndustry] = useState("saas");
  const [cities, setCities] = useState<Array<{ name: string; ar: string }>>([]);
  const [keywordsAr, setKeywordsAr] = useState<string[]>(PRESETS[0].keywords_ar);
  const [keywordsEn, setKeywordsEn] = useState<string[]>(PRESETS[0].keywords_en);
  const [negativeKeywords, setNegativeKeywords] = useState<string[]>(PRESETS[0].negative_keywords);
  const [decisionMakers, setDecisionMakers] = useState<string[]>(PRESETS[0].decision_makers);
  const [notes, setNotes] = useState(PRESETS[0].notes);
  const [minBranches, setMinBranches] = useState(0);

  // New tag inputs
  const [newKwAr, setNewKwAr] = useState("");
  const [newKwEn, setNewKwEn] = useState("");
  const [newNegKw, setNewNegKw] = useState("");
  const [customCityName, setCustomCityName] = useState("");

  // Raw JSON state for the code editor
  const [rawJson, setRawJson] = useState("");
  const [saving, setSaving] = useState(false);

  // Construct current definition object from visual fields
  const currentDefinition = useMemo(() => {
    const cityLabel = cities.length > 0 ? cities.map((c) => c.ar || c.name).join("، ") : "عالمي";
    return {
      industry,
      name: `معايير ${industry} — ${cityLabel}`,
      cities,
      keywords_en: keywordsEn,
      keywords_ar: keywordsAr,
      negative_keywords: negativeKeywords,
      criteria: {
        min_branches: minBranches,
        decision_maker_roles: decisionMakers,
        notes,
      },
      v0_limits: {
        search_results_per_query: 10,
        max_search_queries: Math.max(1, cities.length) * (keywordsAr.length + keywordsEn.length),
        enrichment_budget_credits: 0,
        enrichment_max_people: 0,
      },
    };
  }, [industry, cities, keywordsEn, keywordsAr, negativeKeywords, minBranches, decisionMakers, notes]);

  // Keep rawJson in sync with current definition when in visual mode
  useEffect(() => {
    if (mode === "visual") {
      setRawJson(JSON.stringify(currentDefinition, null, 2));
    }
  }, [currentDefinition, mode]);

  // Apply a preset
  function applyPreset(p: (typeof PRESETS)[0]) {
    setSelectedPresetId(p.id);
    setIndustry(p.industry);
    setKeywordsAr([...p.keywords_ar]);
    setKeywordsEn([...p.keywords_en]);
    setNegativeKeywords([...p.negative_keywords]);
    setDecisionMakers([...p.decision_makers]);
    setNotes(p.notes);
    toast.success(`تم تحميل قالب ${p.label}`);
  }

  // Load active ICP into visual builder
  function loadActiveIntoBuilder() {
    if (!active?.definition) return;
    const d = active.definition;
    if (d.industry) setIndustry(d.industry);
    if (Array.isArray(d.cities)) setCities(d.cities);
    if (Array.isArray(d.keywords_ar)) setKeywordsAr(d.keywords_ar);
    if (Array.isArray(d.keywords_en)) setKeywordsEn(d.keywords_en);
    if (Array.isArray(d.negative_keywords)) setNegativeKeywords(d.negative_keywords);
    if (d.criteria?.notes) setNotes(d.criteria.notes);
    if (typeof d.criteria?.min_branches === "number") setMinBranches(d.criteria.min_branches);
    if (Array.isArray(d.criteria?.decision_maker_roles)) setDecisionMakers(d.criteria.decision_maker_roles);
    setSelectedPresetId("custom");
    setRawJson(JSON.stringify(d, null, 2));
    toast.success("تم استيراد المعايير النشطة إلى المنشئ");
  }

  // City toggling
  function toggleCity(city: { name: string; ar: string }) {
    const exists = cities.some((c) => c.name.toLowerCase() === city.name.toLowerCase());
    if (exists) {
      setCities(cities.filter((c) => c.name.toLowerCase() !== city.name.toLowerCase()));
    } else {
      setCities([...cities, city]);
    }
  }

  function addCustomCity() {
    if (!customCityName.trim()) return;
    const trimmed = customCityName.trim();
    if (cities.some((c) => c.ar === trimmed || c.name.toLowerCase() === trimmed.toLowerCase())) {
      toast.error("هذه المدينة مضافة بالفعل");
      return;
    }
    setCities([...cities, { name: trimmed, ar: trimmed }]);
    setCustomCityName("");
    toast.success(`تمت إضافة مدينة ${trimmed}`);
  }

  // Keyword tag helpers
  function addKwAr() {
    if (!newKwAr.trim()) return;
    const v = newKwAr.trim();
    if (!keywordsAr.includes(v)) setKeywordsAr([...keywordsAr, v]);
    setNewKwAr("");
  }

  function addKwEn() {
    if (!newKwEn.trim()) return;
    const v = newKwEn.trim();
    if (!keywordsEn.includes(v)) setKeywordsEn([...keywordsEn, v]);
    setNewKwEn("");
  }

  function addNegKw() {
    if (!newNegKw.trim()) return;
    const v = newNegKw.trim();
    if (!negativeKeywords.includes(v)) setNegativeKeywords([...negativeKeywords, v]);
    setNewNegKw("");
  }

  // Save & Activate
  async function save() {
    let definition: any;
    if (mode === "json") {
      try {
        definition = JSON.parse(rawJson);
      } catch {
        return toast.error("صيغة JSON غير صالحة، يرجى فحص الأقواس والفواصل");
      }
    } else {
      definition = currentDefinition;
    }

    // cities is optional — empty means global/unrestricted search
    if (!definition.cities) {
      definition.cities = [];
    }

    setSaving(true);
    try {
      await apiPostExtra.icpCreate(definition, "agentic", true, "manual");
      toast.success("تم حفظ المعايير بنجاح وتفعيلها للمهام والبحث القادم!");
      refresh();
    } catch (e) {
      toast.error(friendlyError(e));
    } finally {
      setSaving(false);
    }
  }

  // Activate existing version
  async function activate(id: string) {
    try {
      await apiPostExtra.icpActivate(id);
      toast.success("تم تنشيط هذه النسخة بنجاح — كافة عمليات البحث والتأهيل ستعتمد عليها");
      refresh();
    } catch (e) {
      toast.error(friendlyError(e));
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        icon={<SlidersHorizontal className="h-5 w-5 text-[var(--accent)]" />}
        title="معايير الفلترة والاستهداف (ICP)"
        description="تحديد المعايير والشروط المستهدفة — النسخة النشطة تقود تخطيط محركات البحث، وقواعد التأهيل الحتمي"
        action={
          <div className="flex items-center gap-1.5 p-1 rounded-xl bg-[var(--bg-soft)] border border-[var(--border-soft)]">
            <button
              onClick={() => setMode("visual")}
              className={cn(
                "px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5",
                mode === "visual"
                  ? "bg-[var(--bg-elev)] text-[var(--fg)] shadow-xs"
                  : "text-[var(--fg-muted)] hover:text-[var(--fg)]"
              )}
            >
              <Sparkles className="h-3.5 w-3.5 text-[var(--accent)]" />
              المنشئ المرئي (No-Code)
            </button>
            <button
              onClick={() => setMode("json")}
              className={cn(
                "px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5",
                mode === "json"
                  ? "bg-[var(--bg-elev)] text-[var(--fg)] shadow-xs"
                  : "text-[var(--fg-muted)] hover:text-[var(--fg)]"
              )}
            >
              <FileCode className="h-3.5 w-3.5" />
              محرر JSON المتقدم
            </button>
          </div>
        }
      />

      {/* Active Version Live Banner */}
      <Card className="border-[var(--accent)]/40 bg-gradient-to-r from-[var(--accent)]/5 via-transparent to-transparent">
        <CardContent className="p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-[var(--fg)]">النسخة المعتمدة النشطة حالياً:</span>
              {active ? (
                <Badge variant="success" className="text-xs px-2.5 py-0.5">
                  <CheckCircle2 className="h-3.5 w-3.5 inline me-1" />
                  {active.slug} ({active.version})
                </Badge>
              ) : (
                <Badge variant="warn" className="text-xs">لا يوجد نسخة نشطة — الفلترة الحتمية معطلة</Badge>
              )}
            </div>
            {active?.definition && (
              <div className="flex items-center gap-3 text-xs text-[var(--fg-soft)] flex-wrap pt-0.5">
                <span>القطاع: <strong className="text-[var(--fg)]">{active.definition.industry || "—"}</strong></span>
                <span>·</span>
                <span>المدن: <strong className="text-[var(--fg)]">{active.definition.cities?.map((c: any) => c.ar || c.name).join("، ") || "كل المدن"}</strong></span>
                <span>·</span>
                <span>الكلمات: <strong className="text-[var(--fg)]">{(active.definition.keywords_ar?.length ?? 0) + (active.definition.keywords_en?.length ?? 0)} كلمة</strong></span>
              </div>
            )}
          </div>
          {active?.definition && (
            <Button variant="outline" size="sm" onClick={loadActiveIntoBuilder} className="text-xs shrink-0">
              <RotateCcw className="h-3.5 w-3.5" />
              استيراد هذه النسخة إلى المنشئ
            </Button>
          )}
        </CardContent>
      </Card>

      {/* Builder Workspace */}
      <div className="grid lg:grid-cols-12 gap-5 items-start">
        {/* Left/Main Column: Visual Controls or JSON */}
        <div className="lg:col-span-8 space-y-5">
          {mode === "visual" ? (
            <>
              {/* Step 1: Industry Presets */}
              <Card>
                <CardContent className="p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-[var(--fg)] flex items-center gap-1.5">
                      <Building2 className="h-4 w-4 text-[var(--accent)]" />
                      الخطوة 1: اختيار القطاع المستهدف
                    </span>
                    <span className="text-[11px] text-[var(--fg-muted)]">قوالب جاهزة لأبرز القطاعات</span>
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                    {PRESETS.map((p) => (
                      <button
                        key={p.id}
                        type="button"
                        onClick={() => applyPreset(p)}
                        className={cn(
                          "flex flex-col items-start p-3 rounded-xl border text-right transition-all group",
                          selectedPresetId === p.id
                            ? "bg-[var(--accent-soft)]/50 border-[var(--accent)] shadow-xs ring-1 ring-[var(--accent)]/30"
                            : "bg-[var(--bg-soft)] border-[var(--border-soft)] hover:border-[var(--border)]"
                        )}
                      >
                        <span className="text-xl mb-1">{p.icon}</span>
                        <span className="text-xs font-bold text-[var(--fg)] group-hover:text-[var(--accent)] transition-colors">
                          {p.label}
                        </span>
                        <span className="text-[10px] text-[var(--fg-muted)] mt-0.5 truncate w-full">
                          {p.keywords_ar.slice(0, 2).join("، ")}
                        </span>
                      </button>
                    ))}
                    <button
                      type="button"
                      onClick={() => setSelectedPresetId("custom")}
                      className={cn(
                        "flex flex-col items-start p-3 rounded-xl border text-right transition-all group",
                        selectedPresetId === "custom"
                          ? "bg-[var(--accent-soft)]/50 border-[var(--accent)] shadow-xs ring-1 ring-[var(--accent)]/30"
                          : "bg-[var(--bg-soft)] border-[var(--border-soft)] hover:border-[var(--border)]"
                      )}
                    >
                      <span className="text-xl mb-1">💡</span>
                      <span className="text-xs font-bold text-[var(--fg)] group-hover:text-[var(--accent)] transition-colors">
                        قطاع مخصص
                      </span>
                      <span className="text-[10px] text-[var(--fg-muted)] mt-0.5">تحديد كلمات خاصة</span>
                    </button>
                  </div>
                </CardContent>
              </Card>

              {/* Step 2: Target Locations */}
              <Card>
                <CardContent className="p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-[var(--fg)] flex items-center gap-1.5">
                      <MapPin className="h-4 w-4 text-emerald-400" />
                      الخطوة 2: المدن والمناطق المستهدفة
                    </span>
                    <span className="text-[11px] text-[var(--fg-muted)]">
                      {cities.length === 0 ? "بحث عالمي (غير محدد)" : <>{cities.length} مدينة محددة</>}
                    </span>
                  </div>

                  <div className="flex items-center gap-1.5 flex-wrap">
                    {SUGGESTED_LOCATIONS.map((c) => {
                      const isSelected = cities.some((item) => item.name.toLowerCase() === c.name.toLowerCase());
                      return (
                        <button
                          key={c.name}
                          type="button"
                          onClick={() => toggleCity(c)}
                          className={cn(
                            "inline-flex items-center gap-1.5 h-8 px-3 rounded-full text-xs font-medium transition-all border",
                            isSelected
                              ? "bg-emerald-500/15 border-emerald-500/40 text-emerald-300 font-semibold shadow-xs"
                              : "bg-[var(--bg-soft)] border-[var(--border-soft)] text-[var(--fg-muted)] hover:border-[var(--border)]"
                          )}
                        >
                          {isSelected && <Check className="h-3 w-3 text-emerald-400" />}
                          <span>{c.ar}</span>
                        </button>
                      );
                    })}
                  </div>

                  {/* Add custom city */}
                  <div className="flex items-center gap-2 pt-1 border-t border-[var(--border-soft)]">
                    <span className="text-[11px] text-[var(--fg-muted)] shrink-0">مدينة أخرى:</span>
                    <Input
                      placeholder="مثال: Lagos, Manila, Toronto…"
                      value={customCityName}
                      onChange={(e) => setCustomCityName(e.target.value)}
                      onKeyDown={(e) => { if (e.key === "Enter") addCustomCity(); }}
                      className="text-xs h-8 max-w-xs"
                    />
                    <Button size="sm" variant="outline" onClick={addCustomCity} className="text-xs h-8">
                      <Plus className="h-3 w-3" />
                      إضافة
                    </Button>
                  </div>
                </CardContent>
              </Card>

              {/* Step 3: Keywords & Terms */}
              <Card>
                <CardContent className="p-4 space-y-4">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-[var(--fg)] flex items-center gap-1.5">
                      <Tag className="h-4 w-4 text-[var(--accent)]" />
                      الخطوة 3: الكلمات المفتاحية لمحركات الزحف (Search Queries)
                    </span>
                    <span className="text-[11px] text-[var(--fg-muted)]">عربي وإنجليزي لتحقيق أقصى تغطية</span>
                  </div>

                  {/* Arabic Keywords */}
                  <div className="space-y-2">
                    <label className="text-[11px] font-semibold text-[var(--fg-soft)] block">الكلمات المفتاحية بالعربية:</label>
                    <div className="flex items-center gap-1.5 flex-wrap">
                      {keywordsAr.map((kw, i) => (
                        <span key={i} className="inline-flex items-center gap-1 h-7 px-2.5 rounded-lg bg-[var(--bg-soft)] border border-[var(--border-soft)] text-xs text-[var(--fg)]">
                          {kw}
                          <button
                            type="button"
                            onClick={() => setKeywordsAr(keywordsAr.filter((_, idx) => idx !== i))}
                            className="text-[var(--fg-muted)] hover:text-rose-400"
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </span>
                      ))}
                    </div>
                    <div className="flex items-center gap-2">
                      <Input
                        placeholder="أضف كلمة بحث عربية جديدة واضغط Enter…"
                        value={newKwAr}
                        onChange={(e) => setNewKwAr(e.target.value)}
                        onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addKwAr(); } }}
                        className="text-xs h-8"
                      />
                      <Button size="sm" variant="outline" onClick={addKwAr} className="text-xs h-8 shrink-0">إضافة</Button>
                    </div>
                  </div>

                  {/* English Keywords */}
                  <div className="space-y-2 pt-2 border-t border-[var(--border-soft)]">
                    <label className="text-[11px] font-semibold text-[var(--fg-soft)] block">الكلمات المفتاحية بالإنجليزية (English Terms):</label>
                    <div className="flex items-center gap-1.5 flex-wrap" dir="ltr">
                      {keywordsEn.map((kw, i) => (
                        <span key={i} className="inline-flex items-center gap-1 h-7 px-2.5 rounded-lg bg-[var(--bg-soft)] border border-[var(--border-soft)] text-xs text-[var(--fg)]">
                          {kw}
                          <button
                            type="button"
                            onClick={() => setKeywordsEn(keywordsEn.filter((_, idx) => idx !== i))}
                            className="text-[var(--fg-muted)] hover:text-rose-400"
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </span>
                      ))}
                    </div>
                    <div className="flex items-center gap-2">
                      <Input
                        placeholder="Add english term (e.g. b2b software, fintech) and press Enter…"
                        value={newKwEn}
                        onChange={(e) => setNewKwEn(e.target.value)}
                        onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addKwEn(); } }}
                        className="text-xs h-8"
                        dir="ltr"
                      />
                      <Button size="sm" variant="outline" onClick={addKwEn} className="text-xs h-8 shrink-0">إضافة</Button>
                    </div>
                  </div>

                  {/* Negative / Exclusion Keywords */}
                  <div className="space-y-2 pt-2 border-t border-[var(--border-soft)]">
                    <label className="text-[11px] font-semibold text-rose-400 flex items-center gap-1">
                      <ShieldAlert className="h-3.5 w-3.5" />
                      كلمات الاستبعاد الإلزامية (Negative Keywords - لتفادي المواقع والدلائل الوهمية):
                    </label>
                    <div className="flex items-center gap-1.5 flex-wrap">
                      {negativeKeywords.map((kw, i) => (
                        <span key={i} className="inline-flex items-center gap-1 h-7 px-2 rounded-lg bg-rose-500/10 border border-rose-500/30 text-xs text-rose-300">
                          {kw}
                          <button
                            type="button"
                            onClick={() => setNegativeKeywords(negativeKeywords.filter((_, idx) => idx !== i))}
                            className="text-rose-400 hover:text-white"
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </span>
                      ))}
                    </div>
                    <div className="flex items-center gap-2">
                      <Input
                        placeholder="أضف كلمة استبعاد (مثال: وظائف، منتدى، حراج)…"
                        value={newNegKw}
                        onChange={(e) => setNewNegKw(e.target.value)}
                        onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addNegKw(); } }}
                        className="text-xs h-8"
                      />
                      <Button size="sm" variant="outline" onClick={addNegKw} className="text-xs h-8 shrink-0">إضافة استبعاد</Button>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Step 4: Quality Gates & Notes */}
              <Card>
                <CardContent className="p-4 space-y-3">
                  <span className="text-xs font-bold text-[var(--fg)] flex items-center gap-1.5">
                    <SlidersHorizontal className="h-4 w-4 text-amber-400" />
                    الخطوة 4: شروط الجودة والملاحظات التوجيهية للذكاء الاصطناعي
                  </span>
                  <div>
                    <label className="text-[11px] text-[var(--fg-muted)] block mb-1">ملاحظات الفلترة والتأهيل:</label>
                    <Input
                      value={notes}
                      onChange={(e) => setNotes(e.target.value)}
                      placeholder="مثال: التركيز على الشركات والمنشآت المستقلة ذات الحضور الرقمي النشط…"
                      className="text-xs"
                    />
                  </div>
                </CardContent>
              </Card>
            </>
          ) : (
            /* Advanced JSON Editor */
            <Card>
              <CardContent className="p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-[var(--fg)] flex items-center gap-1.5">
                    <FileCode className="h-4 w-4 text-[var(--accent)]" />
                    محرر الـ JSON المباشر
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    className="text-[11px] h-7"
                    onClick={() => setRawJson(JSON.stringify(PRESETS[0], null, 2))}
                  >
                    استعادة القالب الافتراضي
                  </Button>
                </div>
                <textarea
                  value={rawJson}
                  onChange={(e) => setRawJson(e.target.value)}
                  rows={18}
                  dir="ltr"
                  className="w-full rounded-xl border border-[var(--border-soft)] bg-[var(--bg-soft)] p-3 text-xs leading-5 outline-none focus:border-[var(--accent)] font-mono"
                />
              </CardContent>
            </Card>
          )}
        </div>

        {/* Right Column: Execution Summary & Version History */}
        <div className="lg:col-span-4 space-y-5">
          {/* Action Card */}
          <Card className="border-[var(--accent)]/50 shadow-md">
            <CardContent className="p-4 space-y-4">
              <div className="text-xs font-bold text-[var(--fg)] flex items-center justify-between">
                <span>ملخص خطة الاستهداف:</span>
                <Badge variant="outline" className="text-[10px]">مباشر</Badge>
              </div>

              <div className="space-y-2 text-xs text-[var(--fg-soft)] bg-[var(--bg-soft)] p-3 rounded-xl border border-[var(--border-soft)]">
                <div className="flex items-center justify-between">
                  <span>القطاع:</span>
                  <strong className="text-[var(--fg)]">{industry}</strong>
                </div>
                <div className="flex items-center justify-between">
                  <span>المدن المحددة:</span>
                  <strong className="text-[var(--fg)]">{cities.length} مدن</strong>
                </div>
                <div className="flex items-center justify-between">
                  <span>إجمالي الكلمات:</span>
                  <strong className="text-[var(--fg)]">{keywordsAr.length + keywordsEn.length} كلمة</strong>
                </div>
                <div className="flex items-center justify-between">
                  <span>استعلامات البحث المتوقعة:</span>
                  <strong className="text-emerald-400 font-mono font-bold">
                    {cities.length * (keywordsAr.length + keywordsEn.length)} استعلام
                  </strong>
                </div>
              </div>

              <Button
                variant="primary"
                onClick={save}
                disabled={saving}
                className="w-full py-2.5 text-xs font-bold shadow-md"
              >
                {saving ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    جارٍ الحفظ وتنشيط المعايير…
                  </>
                ) : (
                  <>
                    <Save className="h-4 w-4" />
                    حفظ وتنشيط هذه المعايير فوراً
                  </>
                )}
              </Button>

              <p className="text-[10.5px] text-[var(--fg-muted)] leading-4">
                كل عملية حفظ تنشئ نسخة إصدار مرقمة (Versioned) وتبقى النسخ القديمة محفوظة في السجل مع إمكانية التراجع والتنشيط بضغطة زر واحدة.
              </p>
            </CardContent>
          </Card>

          {/* Version History */}
          <Card>
            <CardContent className="p-4 space-y-3">
              <div className="text-xs font-bold text-[var(--fg)] flex items-center gap-1.5">
                <History className="h-4 w-4 text-[var(--accent)]" />
                سجل الإصدارات والتراجع (Audit Trail)
              </div>

              {loading && !data ? (
                <div className="py-6 flex justify-center"><Spinner className="h-5 w-5" /></div>
              ) : versions.length === 0 ? (
                <div className="text-xs text-[var(--fg-muted)] py-3 text-center">لا توجد إصدارات سابقة بعد.</div>
              ) : (
                <div className="space-y-2 max-h-96 overflow-y-auto pe-1">
                  {versions.map((v) => (
                    <div
                      key={v.icp_version_id}
                      className={cn(
                        "p-2.5 rounded-xl border transition-all text-xs space-y-1.5",
                        v.status === "active"
                          ? "bg-emerald-500/10 border-emerald-500/30"
                          : "bg-[var(--bg-soft)] border-[var(--border-soft)]"
                      )}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-[var(--fg)]">{v.slug} ({v.version})</span>
                        <Badge
                          variant={v.status === "active" ? "success" : v.status === "retired" ? "default" : "info"}
                          className="text-[9px]"
                        >
                          {v.status === "active" ? "نشط حالياً" : "مؤرشف"}
                        </Badge>
                      </div>
                      <div className="flex items-center justify-between text-[10px] text-[var(--fg-muted)]">
                        <span>المصدر: {v.source}</span>
                        <span className="font-mono">{v.created_at?.slice(0, 16)}</span>
                      </div>
                      {v.status !== "active" && (
                        <Button
                          variant="outline"
                          size="sm"
                          className="w-full text-[11px] h-6.5 mt-1"
                          onClick={() => activate(v.icp_version_id)}
                        >
                          <CheckCircle2 className="h-3 w-3" />
                          إعادة تنشيط هذه النسخة
                        </Button>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
