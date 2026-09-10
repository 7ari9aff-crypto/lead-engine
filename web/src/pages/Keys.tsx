import { useState } from "react";
import {
  Key,
  Save,
  Eye,
  EyeOff,
  CheckCircle2,
  XCircle,
  Loader2,
  Plus,
  X,
  ShieldCheck,
  AlertTriangle,
  Sparkles,
  Trash2,
  Activity,
  KeyRound,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge, StatusDot } from "@/components/ui/Badge";
import { Input, Label, Textarea } from "@/components/ui/Input";
import { Spinner, EmptyState } from "@/components/ui/EmptyState";
import { useLiveData } from "@/hooks/useLiveData";
import { apiGet, apiPost, type ProviderRow } from "@/lib/api";
import { toast } from "sonner";
import { cn, formatNumber } from "@/lib/utils";

const KEY_GROUPS: { id: string; label: string; description: string; keys: { env: string; label: string; placeholder?: string; multiline?: boolean }[] }[] = [
  {
    id: "llm",
    label: "نماذج اللغة (LLM)",
    description: "للتفكير والتحليل والتأهيل. الـAgent يستخدم Gemini افتراضيًا — أضف عدة مفاتيح للتدوير.",
    keys: [
      { env: "GEMINI_API_KEY", label: "Google Gemini", placeholder: "AIza…" },
      { env: "GROQ_API_KEY", label: "Groq", placeholder: "gsk_…" },
      { env: "OPENROUTER_API_KEY", label: "OpenRouter", placeholder: "sk-or-…" },
    ],
  },
  {
    id: "search",
    label: "البحث على الإنترنت",
    description: "لاكتشاف الشركات. ترتيب البحث: Tavily → Brave → Exa.",
    keys: [
      { env: "TAVILY_API_KEY", label: "Tavily", placeholder: "tvly-…" },
      { env: "BRAVE_API_KEY", label: "Brave Search", placeholder: "BSA…" },
      { env: "EXA_API_KEY", label: "Exa", placeholder: "exa-…" },
    ],
  },
  {
    id: "data",
    label: "بيانات الشركات والأشخاص",
    description: "Apollo للبحث (0 رصيد) والإثراء (1–9 رصيد/شخص).",
    keys: [
      { env: "APOLLO_API_KEY", label: "Apollo", placeholder: "Apollo API key" },
    ],
  },
  {
    id: "email",
    label: "فحص الإيميلات",
    description: "للتحقق 5-حالات. Hunter و AbstractAPI. لو ما في، الـfallback SMTP محلي.",
    keys: [
      { env: "HUNTER_API_KEY", label: "Hunter", placeholder: "Hunter API key" },
      { env: "ABSTRACT_API_KEY", label: "AbstractAPI", placeholder: "Abstract API key" },
    ],
  },
  {
    id: "supabase",
    label: "قاعدة البيانات",
    description: "Supabase. الـURL والـservice role key. ضروري للمزامنة.",
    keys: [
      { env: "SUPABASE_URL", label: "Supabase URL", placeholder: "https://xxx.supabase.co" },
      { env: "SUPABASE_SERVICE_KEY", label: "Service Role Key", placeholder: "eyJ…" },
    ],
  },
];

export function KeysPage() {
  const { data, loading, refresh } = useLiveData(() => apiGet.providers(), 5000);
  const [values, setValues] = useState<Record<string, string>>({});
  const [reveal, setReveal] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState(false);

  function setVal(env: string, v: string) {
    setValues((s) => ({ ...s, [env]: v }));
  }

  function toggleReveal(env: string) {
    setReveal((s) => ({ ...s, [env]: !s[env] }));
  }

  async function saveAll() {
    // Only send non-empty values
    const payload: Record<string, string> = {};
    for (const [k, v] of Object.entries(values)) {
      if (v && v.trim()) payload[k] = v.trim();
    }
    if (Object.keys(payload).length === 0) {
      toast.info("لم يتم تغيير أي مفتاح");
      return;
    }
    setSaving(true);
    try {
      await apiPost.saveKeys(payload);
      toast.success(`تم حفظ ${Object.keys(payload).length} مفتاح — يدخلون حيّز التنفيذ فورًا`);
      setValues({});
      refresh();
    } catch (e: any) {
      toast.error("فشل الحفظ: " + e.message);
    } finally {
      setSaving(false);
    }
  }

  const providers = data?.providers ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Key className="h-5 w-5 text-[var(--accent)]" />
            مفاتيح API
          </h1>
          <p className="text-sm text-[var(--fg-muted)] mt-1">
            تتخزن في <code dir="ltr">.env</code> (خارج git) وتدخل حيّز التنفيذ فورًا بدون إعادة تشغيل.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="accent" className="text-[10px]">
            <ShieldCheck className="h-3 w-3" /> مُشفّر على السيرفر
          </Badge>
          <Button variant="primary" onClick={saveAll} loading={saving} disabled={Object.keys(values).filter(k => values[k]?.trim()).length === 0}>
            <Save className="h-4 w-4" />
            حفظ المفاتيح
          </Button>
        </div>
      </div>

      {/* Info banner */}
      <div className="rounded-xl border border-[var(--info)]/30 bg-[var(--info)]/8 p-4 flex gap-3">
        <Sparkles className="h-5 w-5 text-[var(--info)] shrink-0 mt-0.5" />
        <div className="text-sm text-[var(--fg-muted)]">
          <strong className="text-[var(--fg)]">دعم متعدد المفاتيح:</strong> تقدر تلصق <b>أكثر من مفتاح في نفس الخانة</b> (كل مفتاح في سطر) — النظام يدوّر بينهم تلقائيًا: أول ما مفتاح يوصل لـ rate-limit ينتقل للذي بعده قبل ما يسيب المزوّد.
          <br />
          <strong className="text-[var(--fg)]">القيم المحفوظة لا تُعاد للمتصفح</strong> — شكلها مُقنّع فقط.
        </div>
      </div>

      {/* Quota Overview — clean, simple per-provider status */}
      {providers.length > 0 && <QuotaOverview providers={providers} />}

      {/* Provider status summary */}
      {providers.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>
              <ShieldCheck className="h-4 w-4 text-[var(--success)]" />
              ملخّص الحالة
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {(["active", "degraded", "exhausted", "disabled"] as const).map((st) => {
                const count = providers.filter((p) => p.status === st).length;
                return (
                  <div key={st} className="rounded-lg p-3 bg-[var(--bg-soft)] border border-[var(--border-soft)]">
                    <div className="flex items-center gap-2 mb-1">
                      <StatusDot status={st} />
                      <span className="text-xs text-[var(--fg-muted)]">{st}</span>
                    </div>
                    <div className="text-xl font-bold tabular-nums">{count}</div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Key groups */}
      {KEY_GROUPS.map((g) => (
        <Card key={g.id}>
          <CardHeader>
            <CardTitle>
              {g.label}
              <Badge variant="outline" className="text-[10px]">{g.keys.length}</Badge>
            </CardTitle>
            <CardDescription>{g.description}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {g.keys.map((k) => {
              const provider = providers.find((p) => p.env_key === k.env);
              const set = provider?.key_state === "set";
              return (
                <div key={k.env} className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <Label className="mb-0 flex items-center gap-2">
                      {k.label}
                      <code className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--bg-soft)]" dir="ltr">
                        {k.env}
                      </code>
                    </Label>
                    <div className="flex items-center gap-2">
                      {set ? (
                        <Badge variant="success" className="text-[10px]">
                          <CheckCircle2 className="h-3 w-3" />
                          محفوظ
                        </Badge>
                      ) : (
                        <Badge variant="warn" className="text-[10px]">
                          <AlertTriangle className="h-3 w-3" />
                          فارغ
                        </Badge>
                      )}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <div className="flex-1 relative">
                      {k.multiline ? (
                        <Textarea
                          rows={3}
                          value={values[k.env] || ""}
                          onChange={(e) => setVal(k.env, e.target.value)}
                          placeholder={set ? "•••••••••••••••• (محفوظ — سيب فاضي للحفاظ)" : k.placeholder || ""}
                          dir="ltr"
                          className="font-mono text-xs"
                        />
                      ) : (
                        <Input
                          type={reveal[k.env] ? "text" : "password"}
                          value={values[k.env] || ""}
                          onChange={(e) => setVal(k.env, e.target.value)}
                          placeholder={set ? "•••••••••••••••• (محفوظ — سيب فاضي للحفاظ)" : k.placeholder || ""}
                          dir="ltr"
                          className="font-mono"
                        />
                      )}
                    </div>
                    <Button
                      size="icon"
                      variant="ghost"
                      onClick={() => toggleReveal(k.env)}
                      title={reveal[k.env] ? "إخفاء" : "إظهار"}
                    >
                      {reveal[k.env] ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </Button>
                  </div>
                </div>
              );
            })}
          </CardContent>
        </Card>
      ))}

      <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-soft)] p-4 text-xs text-[var(--fg-muted)] flex gap-2">
        <AlertTriangle className="h-4 w-4 text-[var(--warn)] shrink-0 mt-0.5" />
        <div>
          <strong className="text-[var(--fg)]">ملاحظة:</strong> سيب الحقل فاضي لو مش عايز تغيّر مفتاح موجود. الحفظ الفوري يحدّث الـProvider Registry ويختار المزوّدات الصحّية في الـRouter.
        </div>
      </div>
    </div>
  );
}

// ============= Quota Overview — clean, simple per-provider status =============
function QuotaOverview({ providers }: { providers: ProviderRow[] }) {
  // Sort: missing first (needs attention), then by remaining
  const sorted = [...providers].sort((a, b) => {
    if (a.key_state === "missing" && b.key_state !== "missing") return -1;
    if (b.key_state === "missing" && a.key_state !== "missing") return 1;
    const aRem = a.quota_limit ? (a.quota_limit - (a.quota_used || 0)) : Infinity;
    const bRem = b.quota_limit ? (b.quota_limit - (b.quota_used || 0)) : Infinity;
    return aRem - bRem;
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <Activity className="h-4 w-4 text-[var(--accent)]" />
          حالة الكوتا
        </CardTitle>
        <CardDescription>
          كل مزوّد · الـunits المستهلكة والـالمتبقية
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          {sorted.map((p, i) => {
            const used = p.quota_used || 0;
            const limit = p.quota_limit;
            const remaining = limit != null ? Math.max(0, limit - used) : null;
            const pct = limit ? (used / limit) * 100 : 0;
            const state = p.status?.toLowerCase() || "unknown";
            const noKey = p.key_state === "missing";
            const exhausted = state === "exhausted" || (limit != null && remaining === 0);
            const low = limit != null && pct >= 80 && !exhausted;

            return (
              <div
                key={i}
                className={cn(
                  "rounded-lg p-3 border transition-colors",
                  noKey
                    ? "border-dashed border-[var(--warn)]/40 bg-[var(--warn)]/5"
                    : exhausted
                    ? "border-[var(--danger)]/40 bg-[var(--danger)]/5"
                    : low
                    ? "border-[var(--warn)]/40 bg-[var(--warn)]/5"
                    : "border-[var(--border-soft)] bg-[var(--bg-soft)]"
                )}
              >
                <div className="flex items-center justify-between gap-3 mb-1.5">
                  <div className="flex items-center gap-2 min-w-0">
                    <StatusDot status={noKey ? "DISABLED" : state} />
                    <span className="font-medium text-sm truncate">{p.name}</span>
                    <Badge variant="outline" className="text-[10px] shrink-0">
                      {p.task}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    {noKey ? (
                      <Badge variant="warn" className="text-[10px]">
                        <KeyRound className="h-3 w-3" />
                        بدون مفتاح
                      </Badge>
                    ) : exhausted ? (
                      <Badge variant="danger" className="text-[10px]">
                        خلصت الرصيد
                      </Badge>
                    ) : low ? (
                      <Badge variant="warn" className="text-[10px]">
                        <AlertTriangle className="h-3 w-3" />
                        قاربت تخلص
                      </Badge>
                    ) : (
                      <Badge variant="success" className="text-[10px]">
                        شغّال
                      </Badge>
                    )}
                  </div>
                </div>

                {noKey ? (
                  <p className="text-xs text-[var(--fg-muted)]">
                    أضف مفتاح من الخانة أدناه لتفعيل هذا المزوّد.
                  </p>
                ) : (
                  <>
                    {/* Progress bar */}
                    <div className="h-1.5 w-full rounded-full bg-[var(--bg)] overflow-hidden">
                      <div
                        className={cn(
                          "h-full rounded-full transition-all",
                          exhausted
                            ? "bg-[var(--danger)]"
                            : low
                            ? "bg-[var(--warn)]"
                            : "bg-[var(--success)]"
                        )}
                        style={{
                          width: limit ? `${Math.min(100, pct)}%` : "0%",
                        }}
                      />
                    </div>

                    {/* Numbers row */}
                    <div className="flex items-center justify-between mt-1.5 text-xs text-[var(--fg-muted)] tabular-nums" dir="ltr">
                      <span>
                        <span className="text-[var(--fg)] font-medium">
                          {formatNumber(used)}
                        </span>{" "}
                        مستخدم
                      </span>
                      <span>
                        {limit != null ? (
                          <>
                            <span className="text-[var(--fg)] font-medium">
                              {formatNumber(remaining)}
                            </span>{" "}
                            متبقي من {formatNumber(limit)}
                          </>
                        ) : (
                          <span className="text-[var(--fg-soft)]">بلا حد أقصى</span>
                        )}
                      </span>
                    </div>
                  </>
                )}
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
