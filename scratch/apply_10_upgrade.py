import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

def update_file(path, replacements):
    full_path = os.path.join(r"d:\lead generation", path)
    with open(full_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    orig = content
    for old, new in replacements:
        if old not in content:
            print(f"[WARN] In {path}: Target string not found: {old[:60]}")
        content = content.replace(old, new)
    
    if content != orig:
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[OK] Updated {path}")
    else:
        print(f"[NOOP] No changes for {path}")

# 1. Update Leads.tsx
update_file("web/src/pages/Leads.tsx", [
    (
        """  MessageCircle,
  FileSpreadsheet,
} from "lucide-react";""",
        """  MessageCircle,
  FileSpreadsheet,
  Send,
} from "lucide-react";"""
    ),
    (
        """import { toast } from "sonner";""",
        """import { toast } from "sonner";
import { parseAndValidatePhone } from "@/lib/phone";
import { logAuditAction } from "@/lib/audit";
import { WebhookExportModal } from "@/components/leads/WebhookExportModal";"""
    ),
    (
        """export function getWhatsAppUrl(phone?: string | null, companyName?: string | null): string | null {
  if (!phone) return null;
  let digits = phone.replace(/[^0-9]/g, "");
  if (digits.startsWith("00")) digits = digits.substring(2);
  if (!digits || digits.length < 7) return null;
  const greeting = `السلام عليكم ورحمة الله، بخصوص خدمات ${companyName || "المنشأة"} الكريمة.. حاب أستفسر من حضرتكم`;
  return `https://wa.me/${digits}?text=${encodeURIComponent(greeting)}`;
}""",
        """export function getWhatsAppUrl(phone?: string | null, companyName?: string | null): string | null {
  return parseAndValidatePhone(phone, companyName).whatsappUrl;
}"""
    ),
    (
        """  const [quickFilter, setQuickFilter] = useState<"all" | "whatsapp" | "verified_email" | "tier_a" | "review" | "accepted">("all");
  const [selectedCity, setSelectedCity] = useState<string>("");""",
        """  const [quickFilter, setQuickFilter] = useState<"all" | "whatsapp" | "verified_email" | "tier_a" | "review" | "accepted">("all");
  const [selectedCity, setSelectedCity] = useState<string>("");
  const [webhookModalOpen, setWebhookModalOpen] = useState(false);"""
    ),
    (
        """    downloadFile(`leads${suffix}_${Date.now()}.csv`, csv, "text/csv;charset=utf-8");
  }""",
        """    downloadFile(`leads${suffix}_${Date.now()}.csv`, csv, "text/csv;charset=utf-8");
    logAuditAction("export.csv", "تنزيل ملف CSV", `تم تصدير ${rows.length} عميل بصيغة CSV`, rows.length);
  }"""
    ),
    (
        """    downloadFile(`leads_instantly_${Date.now()}.csv`, csv, "text/csv;charset=utf-8");
    toast.success(`تم تصدير ${rows.length} عميل بتنسيق Instantly / Smartlead`);
  }""",
        """    downloadFile(`leads_instantly_${Date.now()}.csv`, csv, "text/csv;charset=utf-8");
    toast.success(`تم تصدير ${rows.length} عميل بتنسيق Instantly / Smartlead`);
    logAuditAction("export.instantly", "تصدير Instantly / Smartlead", `تم تصدير ${rows.length} عميل بصيغة مخصصة للـ Cold Email`, rows.length);
  }"""
    ),
    (
        """            <Button
              variant="outline"
              size="sm"
              onClick={() => exportInstantlyCSV(filtered)}
              disabled={filtered.length === 0}
              title="تصدير مهيأ مباشرة لأدوات الإيميل البارد مثل Instantly و Smartlead"
            >
              <FileSpreadsheet className="h-4 w-4 text-emerald-500" />
              تصدير Instantly / Smartlead
            </Button>""",
        """            <Button
              variant="outline"
              size="sm"
              onClick={() => setWebhookModalOpen(true)}
              disabled={filtered.length === 0}
              className="border-[var(--accent)]/40 text-[var(--accent)] hover:bg-[var(--accent)]/10"
              title="ترحيل فوري إلى Zapier أو Make أو n8n أو CRM"
            >
              <Send className="h-4 w-4" />
              إرسال لـ Webhook / CRM
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => exportInstantlyCSV(filtered)}
              disabled={filtered.length === 0}
              title="تصدير مهيأ مباشرة لأدوات الإيميل البارد مثل Instantly و Smartlead"
            >
              <FileSpreadsheet className="h-4 w-4 text-emerald-500" />
              تصدير Instantly / Smartlead
            </Button>"""
    ),
    (
        """          <Button variant="primary" size="sm" onClick={() => exportInstantlyCSV(selectedRows)} className="text-xs">
            <FileSpreadsheet className="h-3.5 w-3.5" />
            تصدير Instantly ({selected.size})
          </Button>""",
        """          <Button variant="primary" size="sm" onClick={() => exportInstantlyCSV(selectedRows)} className="text-xs">
            <FileSpreadsheet className="h-3.5 w-3.5" />
            تصدير Instantly ({selected.size})
          </Button>
          <Button variant="outline" size="sm" onClick={() => setWebhookModalOpen(true)} className="text-xs border-[var(--accent)] text-[var(--accent)] hover:bg-[var(--accent)]/10">
            <Send className="h-3.5 w-3.5" />
            ترحيل Webhook ({selected.size})
          </Button>"""
    ),
    (
        """      {/* Table */}""",
        """      {/* Webhook Export Modal */}
      <WebhookExportModal
        open={webhookModalOpen}
        onClose={() => setWebhookModalOpen(false)}
        leads={selectedRows.length > 0 ? selectedRows : filtered}
        selectedCount={selected.size}
      />

      {/* Table */}"""
    )
])

# 2. Update Activity.tsx to include operator audit trail alongside system events
update_file("web/src/pages/Activity.tsx", [
    (
        """import { apiGet, type ActivityEvent } from "@/lib/api";""",
        """import { apiGet, type ActivityEvent } from "@/lib/api";
import { loadAuditLog, type AuditAction } from "@/lib/audit";"""
    ),
    (
        """type FilterMode = "all" | "job." | "agent." | "approval.";

const FILTERS: { value: FilterMode; label: string }[] = [
  { value: "all", label: "الكل" },
  { value: "job.", label: "المهام" },
  { value: "agent.", label: "الوكلاء" },
  { value: "approval.", label: "الموافقات" },
];""",
        """type FilterMode = "all" | "operator" | "job." | "agent." | "approval.";

const FILTERS: { value: FilterMode; label: string }[] = [
  { value: "all", label: "الكل" },
  { value: "operator", label: "عمليات المشغل (Audit)" },
  { value: "job.", label: "المهام" },
  { value: "agent.", label: "الوكلاء" },
  { value: "approval.", label: "الموافقات" },
];"""
    ),
    (
        """  const events = useMemo<ActivityEvent[]>(() => {
    const raw = data?.events ?? [];
    if (filter === "all") return raw;
    return raw.filter((e) => e.kind.startsWith(filter));
  }, [data, filter]);""",
        """  const auditActions = useMemo(() => loadAuditLog(), [data]);

  const combinedItems = useMemo(() => {
    const rawEvents = data?.events ?? [];
    const auditMapped: ActivityEvent[] = auditActions.map((a) => ({
      id: a.id,
      kind: `operator.${a.kind}`,
      organization_id: "local",
      payload: { title: a.title, desc: a.description, count: a.targetCount },
      created_at: a.timestamp,
    }));

    const all = [...auditMapped, ...rawEvents].sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    );

    if (filter === "all") return all;
    if (filter === "operator") return all.filter((e) => e.kind.startsWith("operator."));
    return all.filter((e) => e.kind.startsWith(filter));
  }, [data, auditActions, filter]);"""
    ),
    (
        """  return (
    <div className="space-y-5">
      <PageHeader
        icon={<ActivityIcon className="h-4 w-4 text-white" />}
        title="سجل النشاط"
        description="خط زمني حي للأحداث، قرارات الوكلاء، وطلبات الموافقة على مستوى المؤسسة"
        action={
          <Button variant="outline" size="sm" onClick={() => refresh()} disabled={loading}>
            <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
            تحديث
          </Button>
        }
      />

      <Card>
        <CardContent className="p-3">
          <FilterPills
            options={FILTERS}
            value={filter}
            onChange={(v) => setFilter(v)}
          />
        </CardContent>
      </Card>

      {loading && !data ? (
        <Card>
          <CardContent className="p-8 text-center text-[var(--fg-muted)]">
            <RefreshCw className="h-5 w-5 animate-spin mx-auto mb-2 text-[var(--accent)]" />
            جاري تحميل الأحداث...
          </CardContent>
        </Card>
      ) : events.length === 0 ? (""",
        """  return (
    <div className="space-y-5">
      <PageHeader
        icon={<ActivityIcon className="h-4 w-4 text-white" />}
        title="سجل النشاط والتدقيق (Audit Trail)"
        description="خط زمني موثق لكافة إجراءات المشغل، عمليات التصدير، قرارات الوكلاء، والمهام المنفذة"
        action={
          <Button variant="outline" size="sm" onClick={() => refresh()} disabled={loading}>
            <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
            تحديث
          </Button>
        }
      />

      <Card>
        <CardContent className="p-3">
          <FilterPills
            options={FILTERS}
            value={filter}
            onChange={(v) => setFilter(v)}
          />
        </CardContent>
      </Card>

      {loading && !data ? (
        <Card>
          <CardContent className="p-8 text-center text-[var(--fg-muted)]">
            <RefreshCw className="h-5 w-5 animate-spin mx-auto mb-2 text-[var(--accent)]" />
            جاري تحميل الأحداث...
          </CardContent>
        </Card>
      ) : combinedItems.length === 0 ? ("""
    ),
    (
        """            {events.map((e) => (""",
        """            {combinedItems.map((e) => ("""
    )
])

print("Applied 10/10 upgrade scripts.")
