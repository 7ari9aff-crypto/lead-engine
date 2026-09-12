import { useState } from "react";
import {
  MailCheck,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  HelpCircle,
  ShieldAlert,
  Loader2,
  Search,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge, StatusDot } from "@/components/ui/Badge";
import { Input, Label } from "@/components/ui/Input";
import { apiPost } from "@/lib/api";
import { toast } from "sonner";
import { friendlyError } from "@/lib/friendly";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/layout/PageHeader";

type Status = "DELIVERABLE" | "RISKY" | "CATCH_ALL" | "INVALID" | "UNKNOWN";

const STATUS_META: Record<Status, { label: string; color: string; description: string; icon: any }> = {
  DELIVERABLE: {
    label: "قابل للتوصيل",
    color: "var(--success)",
    description: "الإيميل موجود ويمكن استلام الرسائل عليه.",
    icon: CheckCircle2,
  },
  RISKY: {
    label: "معرّض للخطر",
    color: "var(--warn)",
    description: "الإيميل موجود لكن عوامل خطر (role email، disposable، إلخ).",
    icon: AlertTriangle,
  },
  CATCH_ALL: {
    label: "دومين مفتوح",
    color: "var(--warn)",
    description: "الدومين يستقبل كل الإيميلات — لا يمكن التأكد من وجود عنوان محدد عليه.",
    icon: ShieldAlert,
  },
  INVALID: {
    label: "غير صالح",
    color: "var(--danger)",
    description: "الإيميل لا يوجد أو تم تعطيله أو عوامل فشل قاطعة.",
    icon: XCircle,
  },
  UNKNOWN: {
    label: "غير معروف",
    color: "var(--fg-soft)",
    description: "تعذّر التحقق — لا يوجد مزوّد أو فشل الاتصال.",
    icon: HelpCircle,
  },
};


const DETAIL_LABELS: Record<string, string> = {
  mx: "سجل استلام البريد",
  smtp: "اتصال سيرفر البريد",
  catch_all: "دومين يقبل كل الرسائل",
  disposable: "بريد مؤقت",
  role_account: "بريد وظيفي عام",
  free_provider: "مزود مجاني",
  reason: "ملاحظة",
  error: "سبب الفحص",
  provider: "المزود",
  score: "درجة الثقة",
};

function friendlyDetails(details: Record<string, unknown>) {
  return Object.entries(details)
    .filter(([, v]) => v != null && v !== "")
    .map(([k, v]) => {
      const label = DETAIL_LABELS[k] ?? k.replace(/_/g, " ");
      let value = typeof v === "boolean" ? (v ? "نعم" : "لا") : String(v);
      if (value.length > 80) value = value.slice(0, 79) + "…";
      return (
        <div key={k} className="flex items-center justify-between gap-3 text-[12px]">
          <span className="text-[var(--fg-muted)]">{label}</span>
          <span className="font-medium tnum">{value}</span>
        </div>
      );
    });
}

export function VerifyPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);

  async function check() {
    if (!email.trim()) {
      toast.warning("اكتب إيميل");
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      const r = await apiPost.verifyEmail(email.trim());
      setResult(r);
    } catch (e) {
      toast.error(friendlyError(e));
    } finally {
      setLoading(false);
    }
  }

  const status: Status | null = result?.status || null;
  const meta = status ? STATUS_META[status] : null;
  const Icon = meta?.icon || HelpCircle;

  return (
    <div className="space-y-6 max-w-3xl mx-auto">
      <PageHeader
        icon={<MailCheck className="h-4 w-4 text-[var(--accent)]" />}
        title="فحص الإيميل"
        description="نتيجة واحدة واضحة من خمس احتمالات — العنوان موجود، موجود مع مخاطر، مش متأكد، غير موجود، أو تعذّر الفحص."
      />

      <Card>
        <CardHeader>
          <CardTitle>فحص جديد</CardTitle>
          <CardDescription>الفحص بيتم عبر مزودات التحقق اللي ضبطتها في صفحة المفاتيح.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-end">
            <div className="flex-1">
              <Label>الإيميل</Label>
              <div className="relative">
                <Search className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--fg-soft)]" />
                <Input
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@clinic.com"
                  dir="ltr"
                  className="ps-10"
                  onKeyDown={(e) => e.key === "Enter" && check()}
                />
              </div>
            </div>
            <Button variant="primary" onClick={check} loading={loading}>
              <MailCheck className="h-4 w-4" />
              افحص
            </Button>
          </div>
        </CardContent>
      </Card>

      {loading && (
        <Card>
          <CardContent className="p-8 flex flex-col items-center gap-2">
            <Loader2 className="h-8 w-8 animate-spin text-[var(--accent)]" />
            <p className="text-sm text-[var(--fg-muted)]">جاري التحقق عبر المزوّدين…</p>
          </CardContent>
        </Card>
      )}

      {result && meta && !loading && (
        <Card className="animate-slide-up">
          <CardHeader>
            <CardTitle>
              <Icon className="h-5 w-5" style={{ color: meta.color }} />
              <span style={{ color: meta.color }}>{meta.label}</span>
              <Badge
                variant={
                  status === "DELIVERABLE" ? "success" :
                  status === "RISKY" || status === "CATCH_ALL" ? "warn" :
                  status === "INVALID" ? "danger" : "default"
                }
              >
                <StatusDot status={status!} />
                {meta.label}
              </Badge>
            </CardTitle>
            <CardDescription className="font-mono" dir="ltr">
              {result.email}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-[var(--fg-muted)]">{meta.description}</p>

            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm">
              <Field label="الثقة" value={result.confidence ? `${(result.confidence * 100).toFixed(0)}%` : "—"} />
              <Field label="عبر" value={result.via || result.provider || "—"} />
              <Field
                label="MX"
                value={
                  result.details?.mx
                    ? result.details.mx === "valid"
                      ? "✔ موجود"
                      : "✗ مفقود"
                    : "—"
                }
              />
            </div>

            {result.details && Object.keys(result.details).length > 0 && (
              <details className="rounded-lg border border-[var(--border)] bg-[var(--bg-soft)] overflow-hidden">
                <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-[var(--fg-muted)] hover:bg-[var(--bg-hover)]">
                  تفاصيل الفحص
                </summary>
                <div className="px-3 py-2 space-y-1.5">
                  {friendlyDetails(result.details)}
                </div>
              </details>
            )}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>دلالات الحالات</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2.5">
            {Object.entries(STATUS_META).map(([k, m]) => {
              const I = m.icon;
              return (
                <div key={k} className="flex items-start gap-3 p-2.5 rounded-lg hover:bg-[var(--bg-hover)]">
                  <I className="h-4 w-4 shrink-0 mt-0.5" style={{ color: m.color }} />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium flex items-center gap-2">
                      <span style={{ color: m.color }}>{m.label}</span>
                    </div>
                    <p className="text-xs text-[var(--fg-muted)] mt-0.5">{m.description}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function Field({ label, value }: { label: string; value: any }) {
  return (
    <div className="rounded-lg p-2.5 bg-[var(--bg-soft)] border border-[var(--border-soft)]">
      <div className="text-[10px] text-[var(--fg-soft)] mb-0.5">{label}</div>
      <div className="text-sm font-medium" dir="ltr">{value}</div>
    </div>
  );
}
