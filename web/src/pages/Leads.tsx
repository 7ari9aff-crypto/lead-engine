import { useState, useMemo, useCallback, useEffect } from "react";
import {
  Database,
  Download,
  Search,
  ExternalLink,
  Mail,
  Phone,
  Globe,
  User,
  Building2,
  TrendingUp,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  BookmarkPlus,
  Bookmark,
  X,
  MailCheck,
  Trash2,
  Loader2,
  ChevronDown,
  Briefcase,
  ShieldCheck,
  Sparkles,
  Copy,
  Check,
  MessageCircle,
  FileSpreadsheet,
  Send,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge, StatusDot } from "@/components/ui/Badge";
import { Input, Select } from "@/components/ui/Input";
import { useLiveData } from "@/hooks/useLiveData";
import { apiGet, apiPost, apiPitch, type LeadRow, type PitchData } from "@/lib/api";
import { downloadFile, formatNumber, truncate, cn } from "@/lib/utils";
import { friendlyError, ICP_LABELS } from "@/lib/friendly";
import { Spinner, EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatCard } from "@/components/ui/FilterPills";
import { ReviewPanel } from "@/components/review/ReviewPanel";
import { toast } from "sonner";
import { parseAndValidatePhone } from "@/lib/phone";
import { logAuditAction } from "@/lib/audit";
import { WebhookExportModal } from "@/components/leads/WebhookExportModal";

// Saved searches — persisted locally per browser.
const SAVED_KEY = "leadEngine.savedSearches";
type SavedSearch = { name: string; search: string; stage: string; jobId: string };

function loadSaved(): SavedSearch[] {
  try {
    return JSON.parse(localStorage.getItem(SAVED_KEY) || "[]");
  } catch {
    return [];
  }
}

export function getWhatsAppUrl(phone?: string | null, companyName?: string | null): string | null {
  return parseAndValidatePhone(phone, companyName).whatsappUrl;
}

export function LeadsPage() {
  const { data, loading, error, refresh } = useLiveData(() => apiGet.leads({ limit: 500 }), 5000);
  const [search, setSearch] = useState("");
  const [stage, setStage] = useState("");
  const [jobId, setJobId] = useState("");
  const [saved, setSaved] = useState<SavedSearch[]>(loadSaved);
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveName, setSaveName] = useState("");
  // Selection is keyed by stable lead identity (NOT row index) so polling
  // refetches or filter changes can never re-point a selection at another row.
  const leadKey = (l: LeadRow, i: number) => l.lead_id || `${l.name}|${l.job_id}|${i}`;
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [drawerLead, setDrawerLead] = useState<LeadRow | null>(null);
  const [bulkBusy, setBulkBusy] = useState<string | null>(null);
  const [bulkProgress, setBulkProgress] = useState<string | null>(null);
  const [quickFilter, setQuickFilter] = useState<"all" | "whatsapp" | "verified_email" | "tier_a" | "review" | "accepted">("all");
  const [selectedCity, setSelectedCity] = useState<string>("");
  const [webhookModalOpen, setWebhookModalOpen] = useState(false);

  const leads = data ?? [];
  const jobs = Array.from(new Set(leads.map((l) => l.job_id).filter(Boolean))) as string[];
  const availableCities = useMemo(() => Array.from(new Set(leads.map((l) => l.city).filter(Boolean))) as string[], [leads]);

  useEffect(() => { setSelected(new Set()); }, [search, stage, jobId, quickFilter, selectedCity]);

  const filtered = useMemo(() => {
    return leads.filter((l) => {
      if (stage && l.stage !== stage) return false;
      if (jobId && l.job_id !== jobId) return false;
      if (selectedCity && l.city !== selectedCity) return false;
      if (quickFilter === "whatsapp" && !getWhatsAppUrl(l.phone, l.name)) return false;
      if (quickFilter === "verified_email" && !(l.email && l.email_status === "DELIVERABLE")) return false;
      if (quickFilter === "tier_a" && !((l.score ?? 0) >= 80 || (l.tier && l.tier.toUpperCase().startsWith("A")))) return false;
      if (quickFilter === "review" && l.stage !== "REVIEW") return false;
      if (quickFilter === "accepted" && l.stage !== "ACCEPTED") return false;
      if (search) {
        const q = search.toLowerCase();
        return (
          (l.name || "").toLowerCase().includes(q) ||
          (l.city || "").toLowerCase().includes(q) ||
          (l.domain || "").toLowerCase().includes(q) ||
          (l.email || "").toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [leads, search, stage, jobId, selectedCity, quickFilter]);

  const stats = useMemo(() => {
    return {
      total: leads.length,
      accepted: leads.filter((l) => l.stage === "ACCEPTED").length,
      review: leads.filter((l) => l.stage === "REVIEW").length,
      rejected: leads.filter((l) => l.stage === "REJECTED").length,
    };
  }, [leads]);

  const saveSearch = useCallback(() => {
    const name = saveName.trim() || `بحث ${saved.length + 1}`;
    const entry: SavedSearch = { name, search, stage, jobId };
    const next = [...saved.filter((s) => s.name !== name), entry].slice(-8);
    setSaved(next);
    localStorage.setItem(SAVED_KEY, JSON.stringify(next));
    setSaveName("");
    setSaveOpen(false);
    toast.success(`تم حفظ البحث "${name}"`);
  }, [saveName, search, stage, jobId, saved]);

  function applySaved(s: SavedSearch) {
    setSearch(s.search);
    setStage(s.stage);
    setJobId(s.jobId);
    setSelected(new Set());
  }

  function removeSaved(name: string) {
    const next = saved.filter((s) => s.name !== name);
    setSaved(next);
    localStorage.setItem(SAVED_KEY, JSON.stringify(next));
  }

  function exportCSV(rows: LeadRow[], suffix = "") {
    if (rows.length === 0) return;
    const headers = [
      "name", "city", "domain", "website", "phone", "email", "email_status",
      "decision_maker", "tier", "score", "stage", "legal_status", "job_id",
    ];
    const csvRows = rows.map((l) =>
      headers.map((h) => `"${String((l as any)[h] ?? "").replace(/"/g, '""')}"`).join(",")
    );
    const csv = [headers.join(","), ...csvRows].join("\n");
    downloadFile(`leads${suffix}_${Date.now()}.csv`, csv, "text/csv;charset=utf-8");
    logAuditAction("export.csv", "تنزيل ملف CSV", `تم تصدير ${rows.length} عميل بصيغة CSV`, rows.length);
  }

  function exportInstantlyCSV(rows: LeadRow[]) {
    if (rows.length === 0) return;
    const headers = [
      "email", "first_name", "company_name", "website", "phone", "city", "custom_icebreaker"
    ];
    const csvRows = rows.map((l) => {
      const dm = l.decision_maker || "المدير التنفيذي / المسؤول";
      const icebreaker = `لفت انتباهي تميز ونمو ${l.name}${l.city ? ` في ${l.city}` : ""}`;
      return [
        `"${String(l.email || "").replace(/"/g, '""')}"`,
        `"${String(dm).replace(/"/g, '""')}"`,
        `"${String(l.name || "").replace(/"/g, '""')}"`,
        `"${String(l.website || l.domain || "").replace(/"/g, '""')}"`,
        `"${String(l.phone || "").replace(/"/g, '""')}"`,
        `"${String(l.city || "").replace(/"/g, '""')}"`,
        `"${String(icebreaker).replace(/"/g, '""')}"`,
      ].join(",");
    });
    const csv = [headers.join(","), ...csvRows].join("\n");
    downloadFile(`leads_instantly_${Date.now()}.csv`, csv, "text/csv;charset=utf-8");
    toast.success(`تم تصدير ${rows.length} عميل بتنسيق Instantly / Smartlead`);
    logAuditAction("export.instantly", "تصدير Instantly / Smartlead", `تم تصدير ${rows.length} عميل بصيغة مخصصة للـ Cold Email`, rows.length);
  }


  const selectedRows = filtered.filter((l, i) => selected.has(leadKey(l, i)));

  function toggleAll() {
    if (selectedRows.length === filtered.length && filtered.length > 0) setSelected(new Set());
    else setSelected(new Set(filtered.map((l, i) => leadKey(l, i))));
  }

  async function bulkVerify() {
    setBulkBusy("verify");
    const targets = selectedRows.filter((l) => l.email);
    let ok = 0, bad = 0;
    for (const l of targets) {
      try {
        await apiPost.verifyEmail(l.email!);
        ok += 1;
      } catch {
        bad += 1;
      }
      setBulkProgress(`${ok + bad}/${targets.length}`);
    }
    setBulkBusy(null);
    setBulkProgress(null);
    if (ok === 0 && targets.length > 0) {
      toast.error("كل محاولات الفحص فشلت — راجع مفاتيح مزود التحقق أو جرّب تاني");
    } else {
      toast.success(`تم فحص ${ok} إيميل${bad ? ` — وفشل ${bad}` : ""}، والنتائج بتتحدث في القايمة`);
    }
    refresh();
  }

  async function bulkDelete() {
    const deletable = selectedRows.filter((l) => l.lead_id);
    if (deletable.length === 0) return;
    if (!confirm(`هيتم حذف ${deletable.length} عميل نهائيًا مع أدلتهم — مفيش رجعة. متأكد؟`)) return;
    setBulkBusy("delete");
    let ok = 0;
    for (const l of deletable) {
      try {
        await apiPost.deleteLead(l.lead_id!);
        ok += 1;
      } catch { /* skip and continue */ }
    }
    setBulkBusy(null);
    setSelected(new Set());
    toast.success(`تم حذف ${ok} عميل`);
    refresh();
  }

  async function bulkApprove() {
    const targets = selectedRows.filter((l) => l.lead_id);
    if (targets.length === 0) return;
    setBulkBusy("approve");
    let ok = 0;
    for (const l of targets) {
      try {
        await apiPost.leadDecision(l.lead_id!, "APPROVE_CONTACT");
        ok += 1;
      } catch { /* continue */ }
    }
    setBulkBusy(null);
    setSelected(new Set());
    toast.success(`تم اعتماد ${ok} عميل للتواصل النهائي`);
    refresh();
  }

  async function bulkReject() {
    const targets = selectedRows.filter((l) => l.lead_id);
    if (targets.length === 0) return;
    setBulkBusy("reject");
    let ok = 0;
    for (const l of targets) {
      try {
        await apiPost.leadDecision(l.lead_id!, "REJECT");
        ok += 1;
      } catch { /* continue */ }
    }
    setBulkBusy(null);
    setSelected(new Set());
    toast.success(`تم استبعاد ${ok} عميل`);
    refresh();
  }

  return (
    <div className="space-y-6">
      <PageHeader
        icon={<Database className="h-4 w-4 text-[var(--accent)]" />}
        title="العملاء المحتملون"
        description={`${formatNumber(stats.total)} إجمالي · ${formatNumber(stats.accepted)} مقبولة · ${formatNumber(stats.review)} مراجعة · ${formatNumber(stats.rejected)} مرفوضة`}
        action={
          <div className="flex items-center gap-2 flex-wrap">
            <Button
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
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={() => exportCSV(filtered)}
              disabled={filtered.length === 0}
            >
              <Download className="h-4 w-4" />
              تنزيل CSV ({filtered.length})
            </Button>
          </div>
        }
      />

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard icon={CheckCircle2} label="مقبولة" value={stats.accepted} tone="success" />
        <StatCard icon={AlertTriangle} label="مراجعة" value={stats.review} tone="warn" />
        <StatCard icon={XCircle} label="مرفوضة" value={stats.rejected} tone="danger" />
        <StatCard icon={TrendingUp} label="إجمالي" value={stats.total} tone="accent" />
      </div>

      {/* Filters + saved searches */}
      <Card>
        <CardContent className="p-3 space-y-2.5">
          {/* Quick Smart Filters Bar */}
          <div className="flex items-center gap-1.5 flex-wrap pb-2 border-b border-[var(--border-soft)]">
            <span className="text-[11px] font-semibold text-[var(--fg-muted)] shrink-0 me-1">تصفية سريعة:</span>
            {[
              { id: "all", label: "الكل", count: leads.length },
              { id: "whatsapp", label: "📱 له واتساب", count: leads.filter((l) => getWhatsAppUrl(l.phone, l.name)).length },
              { id: "verified_email", label: "✉️ إيميل صالح", count: leads.filter((l) => l.email && l.email_status === "DELIVERABLE").length },
              { id: "tier_a", label: "⭐ النخبة (Tier A)", count: leads.filter((l) => (l.score ?? 0) >= 80 || l.tier?.toUpperCase().startsWith("A")).length },
              { id: "review", label: "🔍 مراجعة", count: leads.filter((l) => l.stage === "REVIEW").length },
              { id: "accepted", label: "✅ معتمد", count: leads.filter((l) => l.stage === "ACCEPTED").length },
            ].map((p) => (
              <button
                key={p.id}
                onClick={() => setQuickFilter(p.id as any)}
                className={cn(
                  "inline-flex items-center gap-1.5 h-7 px-2.5 rounded-full text-xs font-medium transition-all",
                  quickFilter === p.id
                    ? "bg-[var(--accent)] text-white shadow-xs font-semibold"
                    : "bg-[var(--bg-soft)] text-[var(--fg-soft)] hover:text-[var(--fg)] border border-[var(--border-soft)]"
                )}
              >
                <span>{p.label}</span>
                <span className={cn(
                  "text-[10px] px-1.5 py-0.2 rounded-full",
                  quickFilter === p.id ? "bg-white/20 text-white" : "bg-[var(--bg-elev)] text-[var(--fg-muted)]"
                )}>
                  {p.count}
                </span>
              </button>
            ))}

            {/* City Chips */}
            {availableCities.length > 0 && (
              <div className="ms-auto flex items-center gap-1 flex-wrap">
                <span className="text-[10px] text-[var(--fg-muted)]">المدينة:</span>
                {availableCities.map((city) => (
                  <button
                    key={city}
                    onClick={() => setSelectedCity(selectedCity === city ? "" : city)}
                    className={cn(
                      "text-[11px] h-6 px-2 rounded-md font-medium transition-colors border",
                      selectedCity === city
                        ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent-hover)] font-bold"
                        : "border-[var(--border-soft)] bg-[var(--bg-soft)] text-[var(--fg-muted)] hover:border-[var(--border)]"
                    )}
                  >
                    {city}
                  </button>
                ))}
                {selectedCity && (
                  <button
                    onClick={() => setSelectedCity("")}
                    className="text-[10px] text-rose-400 hover:underline px-1"
                  >
                    إلغاء الفلتر
                  </button>
                )}
              </div>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-2 pt-1">
            <div className="relative flex-1 min-w-[200px]">
              <Search className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--fg-soft)]" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="ابحث بالاسم، المدينة، الإيميل…"
                className="ps-10"
              />
            </div>
            <Select value={stage} onChange={(e) => setStage(e.target.value)} className="w-40">
              <option value="">كل المراحل</option>
              <option value="ACCEPTED">مقبولة</option>
              <option value="REVIEW">مراجعة</option>
              <option value="REJECTED">مرفوضة</option>
            </Select>
            {jobs.length > 0 && (
              <Select value={jobId} onChange={(e) => setJobId(e.target.value)} className="w-48">
                <option value="">كل المهام</option>
                {jobs.map((j) => (
                  <option key={j} value={j!}>
                    {ICP_LABELS[j!] ?? "مهمة توليد عملاء"}
                  </option>
                ))}
              </Select>
            )}
            {saveOpen ? (
              <div className="flex items-center gap-1.5">
                <Input
                  value={saveName}
                  onChange={(e) => setSaveName(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") saveSearch(); }}
                  placeholder="اسم البحث…"
                  className="w-36 h-9"
                  autoFocus
                />
                <Button variant="primary" size="sm" onClick={saveSearch}>
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  حفظ
                </Button>
                <Button variant="ghost" size="icon-sm" onClick={() => setSaveOpen(false)}>
                  <X className="h-4 w-4" />
                </Button>
              </div>
            ) : (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setSaveOpen(true)}
                disabled={!search && !stage && !jobId}
                title="احفظ الفلاتر الحالية كبحث جاهز"
              >
                <BookmarkPlus className="h-3.5 w-3.5" />
                احفظ البحث
              </Button>
            )}
          </div>
          {saved.length > 0 && (
            <div className="flex items-center gap-1.5 flex-wrap pt-1">
              <Bookmark className="h-3.5 w-3.5 text-[var(--fg-soft)]" />
              {saved.map((s) => (
                <span
                  key={s.name}
                  className={cn(
                    "inline-flex items-center gap-1.5 h-7 pl-2.5 pr-1.5 rounded-full border text-[11px] font-medium transition-colors",
                    search === s.search && stage === s.stage && jobId === s.jobId
                      ? "bg-[var(--accent-soft)] border-[var(--accent)] text-[var(--accent-hover)]"
                      : "border-[var(--border-soft)] bg-[var(--bg-soft)] text-[var(--fg-muted)] hover:border-[var(--border)]"
                  )}
                >
                  <button onClick={() => applySaved(s)}>{s.name}</button>
                  <button onClick={() => removeSaved(s.name)} title="حذف البحث المحفوظ" aria-label={`حذف البحث المحفوظ: ${s.name}`} className="hover:text-[var(--danger)]">
                    <X className="h-3 w-3" />
                  </button>
                </span>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Sticky Floating Dock for Bulk Operations */}
      {selected.size > 0 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 flex items-center gap-2 px-5 py-3 rounded-2xl bg-[var(--bg-elev)]/95 border border-[var(--accent)] shadow-2xl backdrop-blur-md animate-slide-up flex-wrap justify-center max-w-[95vw]">
          <span className="text-xs font-bold text-[var(--fg)] flex items-center gap-1.5 pe-2 border-e border-[var(--border)]">
            <span className="h-2 w-2 rounded-full bg-[var(--accent)] animate-pulse" />
            تم تحديد {selected.size} من {filtered.length}
          </span>
          <Button variant="primary" size="sm" onClick={() => exportInstantlyCSV(selectedRows)} className="text-xs">
            <FileSpreadsheet className="h-3.5 w-3.5" />
            تصدير Instantly ({selected.size})
          </Button>
          <Button variant="outline" size="sm" onClick={() => setWebhookModalOpen(true)} className="text-xs border-[var(--accent)] text-[var(--accent)] hover:bg-[var(--accent)]/10">
            <Send className="h-3.5 w-3.5" />
            ترحيل Webhook ({selected.size})
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={bulkApprove}
            disabled={bulkBusy != null}
            className="text-xs text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/10"
          >
            {bulkBusy === "approve" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
            اعتماد المحددين
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={bulkReject}
            disabled={bulkBusy != null}
            className="text-xs text-rose-400 border-rose-500/30 hover:bg-rose-500/10"
          >
            {bulkBusy === "reject" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <XCircle className="h-3.5 w-3.5" />}
            استبعاد المحددين
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={bulkBusy != null || !selectedRows.some((l) => l.email)}
            onClick={bulkVerify}
            className="text-xs"
          >
            {bulkBusy === "verify" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <MailCheck className="h-3.5 w-3.5" />}
            فحص الإيميلات{bulkProgress ? ` ${bulkProgress}` : ""}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="text-[var(--danger)] text-xs hover:bg-[var(--danger)]/10"
            disabled={bulkBusy != null || !selectedRows.some((l) => l.lead_id)}
            onClick={bulkDelete}
          >
            {bulkBusy === "delete" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
            حذف
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setSelected(new Set())} className="text-xs text-[var(--fg-muted)]">
            إلغاء التحديد
          </Button>
        </div>
      )}

      {/* Webhook Export Modal */}
      <WebhookExportModal
        open={webhookModalOpen}
        onClose={() => setWebhookModalOpen(false)}
        leads={selectedRows.length > 0 ? selectedRows : filtered}
        selectedCount={selected.size}
      />

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          {loading && !data ? (
            <div className="flex items-center justify-center py-20">
              <Spinner className="h-6 w-6 text-[var(--accent)]" />
            </div>
          ) : error && !data ? (
            <EmptyState
              icon={<XCircle className="h-8 w-8 text-[var(--danger)]" />}
              title="تعذر تحميل العملاء المحتملين"
              description={friendlyError(error)}
              action={
                <Button variant="outline" size="sm" onClick={() => void refresh()}>
                  <Search className="h-3.5 w-3.5" />
                  إعادة المحاولة
                </Button>
              }
              className="m-4"
            />
          ) : filtered.length === 0 ? (
            <EmptyState
              icon={<Database className="h-8 w-8" />}
              title="لا يوجد عملاء محتملون بعد"
              description="شغّل مهمة من صفحة المهام وستظهر النتائج هنا تلقائيًا"
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="pro-table">
                <thead>
                  <tr>
                    <th className="w-8">
                      <input
                        type="checkbox"
                        checked={selectedRows.length === filtered.length && filtered.length > 0}
                        onChange={toggleAll}
                        className="accent-[var(--accent)]"
                        title="تحديد الكل"
                        aria-label="تحديد كل العملاء الظاهرين"
                      />
                    </th>
                    <th>الاسم</th>
                    <th>المدينة</th>
                    <th>الموقع</th>
                    <th>الإيميل</th>
                    <th>صانع القرار</th>
                    <th>الدرجة</th>
                    <th>المرحلة</th>
                    <th className="w-8"></th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((l, i) => (
                    <LeadRowBlock
                      key={leadKey(l, i)}
                      lead={l}
                      selected={selected.has(leadKey(l, i))}
                      onToggleSelect={() => {
                        const next = new Set(selected);
                        const k = leadKey(l, i);
                        if (next.has(k)) next.delete(k);
                        else next.add(k);
                        setSelected(next);
                      }}
                      onOpenDrawer={() => setDrawerLead(l)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export function SocialBadges({
  social,
  linkedin,
}: {
  social?: string | null;
  linkedin?: string | null;
}) {
  const links: { type: string; url: string; label: string; color: string; bg: string }[] = [];

  if (linkedin) {
    links.push({
      type: "linkedin",
      url: linkedin.startsWith("http") ? linkedin : `https://${linkedin}`,
      label: "LinkedIn",
      color: "text-sky-400",
      bg: "bg-sky-500/10 border-sky-500/30",
    });
  }

  if (social) {
    try {
      const parsed = typeof social === "string" ? JSON.parse(social) : social;
      if (typeof parsed === "object" && parsed !== null) {
        for (const [k, v] of Object.entries(parsed)) {
          if (typeof v === "string" && v) {
            const kl = k.toLowerCase();
            const url = v.startsWith("http") ? v : `https://${v}`;
            if (kl.includes("insta")) {
              links.push({ type: "instagram", url, label: "إنستقرام", color: "text-rose-400", bg: "bg-rose-500/10 border-rose-500/30" });
            } else if (kl.includes("snap")) {
              links.push({ type: "snapchat", url, label: "سناب شات", color: "text-yellow-300", bg: "bg-yellow-500/10 border-yellow-500/30" });
            } else if (kl.includes("tik")) {
              links.push({ type: "tiktok", url, label: "تيك توك", color: "text-teal-400", bg: "bg-teal-500/10 border-teal-500/30" });
            } else if (kl.includes("twit") || kl === "x") {
              links.push({ type: "x", url, label: "X", color: "text-blue-400", bg: "bg-blue-500/10 border-blue-500/30" });
            } else if (kl.includes("map") || kl.includes("google")) {
              links.push({ type: "maps", url, label: "خرائط", color: "text-emerald-400", bg: "bg-emerald-500/10 border-emerald-500/30" });
            }
          }
        }
      }
    } catch {
      const sl = social.toLowerCase();
      const url = social.startsWith("http") ? social : `https://${social}`;
      if (sl.includes("instagram.com")) links.push({ type: "instagram", url, label: "إنستقرام", color: "text-rose-400", bg: "bg-rose-500/10 border-rose-500/30" });
      else if (sl.includes("snapchat.com")) links.push({ type: "snapchat", url, label: "سناب شات", color: "text-yellow-300", bg: "bg-yellow-500/10 border-yellow-500/30" });
      else if (sl.includes("tiktok.com")) links.push({ type: "tiktok", url, label: "تيك توك", color: "text-teal-400", bg: "bg-teal-500/10 border-teal-500/30" });
      else if (sl.includes("twitter.com") || sl.includes("x.com")) links.push({ type: "x", url, label: "X", color: "text-blue-400", bg: "bg-blue-500/10 border-blue-500/30" });
    }
  }

  if (links.length === 0) return null;

  return (
    <div className="flex items-center gap-1 mt-1 flex-wrap">
      {links.map((item, idx) => (
        <a
          key={idx}
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(e) => e.stopPropagation()}
          className={cn(
            "inline-flex items-center px-1.5 py-0.2 rounded text-[9px] font-medium border transition-colors hover:opacity-80",
            item.color,
            item.bg
          )}
          title={item.label}
        >
          {item.label}
        </a>
      ))}
    </div>
  );
}

function LeadRowBlock({ lead, selected, onToggleSelect, onOpenDrawer }: {
  lead: LeadRow;
  selected: boolean;
  onToggleSelect: () => void;
  onOpenDrawer: () => void;
}) {
  const l = lead;
  return (
    <tr className={cn(selected && "bg-[var(--accent-soft)]/50")}>
        <td>
          <input
            type="checkbox"
            checked={selected}
            onChange={onToggleSelect}
            className="accent-[var(--accent)]"
          />
        </td>
        <td>
          <button onClick={onOpenDrawer} className="flex items-center gap-2 text-right group" title="اعرض التفاصيل الكاملة">
            <Building2 className="h-3.5 w-3.5 text-[var(--fg-soft)] shrink-0" />
            <span>
              <span className="font-medium group-hover:text-[var(--accent)] transition-colors block">{l.name || "—"}</span>
              {l.phone && (() => {
                const pInfo = parseAndValidatePhone(l.phone, l.name);
                return (
                  <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
                    <span className="text-[10px] text-[var(--fg-muted)] flex items-center gap-1 font-mono" dir="ltr">
                      <Phone className="h-2.5 w-2.5" /> {pInfo.e164 || l.phone}
                    </span>
                    {pInfo.whatsappUrl && (
                      <a
                        href={pInfo.whatsappUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="inline-flex items-center gap-1 px-1.5 py-0.2 rounded text-[10px] font-medium bg-emerald-500/15 text-emerald-400 hover:bg-emerald-500/25 transition-colors border border-emerald-500/30"
                        title={pInfo.statusLabel}
                      >
                        <MessageCircle className="h-2.5 w-2.5" />
                        واتساب
                      </a>
                    )}
                    {pInfo.countryCode && pInfo.country !== "—" && (
                      <span className="text-[9px] text-[var(--fg-muted)] px-1 rounded bg-[var(--bg-soft)] border border-[var(--border-soft)]">
                        {pInfo.country}
                      </span>
                    )}
                  </div>
                );
              })()}
            </span>
          </button>
        </td>
        <td className="text-xs">{l.city || "—"}</td>
        <td>
          {l.domain ? (
            <div>
              <a
                href={`https://${l.domain}`}
                target="_blank"
                rel="noopener"
                className="text-xs text-[var(--accent)] hover:underline flex items-center gap-1 max-w-[140px]"
                dir="ltr"
              >
                <Globe className="h-3 w-3 shrink-0" />
                {truncate(l.domain, 20)}
                <ExternalLink className="h-2.5 w-2.5" />
              </a>
              <SocialBadges social={l.social} linkedin={l.linkedin} />
            </div>
          ) : (
            <div>
              <span className="text-xs text-[var(--fg-muted)]">—</span>
              <SocialBadges social={l.social} linkedin={l.linkedin} />
            </div>
          )}
        </td>
        <td className="text-xs">
          {l.email ? (
            <div className="flex flex-col gap-0.5">
              <a
                href={`mailto:${l.email}`}
                className="text-[var(--accent)] hover:underline flex items-center gap-1"
                dir="ltr"
              >
                <Mail className="h-3 w-3" />
                {truncate(l.email, 22)}
              </a>
              {l.email_status && (
                <Badge variant={l.email_status === "DELIVERABLE" ? "success" : "warn"} className="text-[9px] w-fit">
                  {l.email_status === "DELIVERABLE" ? "صالح" : l.email_status === "INVALID" ? "غير صالح" : "محتاج مراجعة"}
                </Badge>
              )}
            </div>
          ) : (
            "—"
          )}
        </td>
        <td className="text-xs">
          {l.decision_maker ? (
            <div className="flex items-center gap-1">
              <User className="h-3 w-3 text-[var(--fg-soft)]" />
              {truncate(l.decision_maker, 22)}
            </div>
          ) : (
            "—"
          )}
        </td>
        <td>
          {l.score != null ? (
            <div className="flex items-center gap-2">
              <span className="font-bold tabular-nums text-sm">{l.score.toFixed(0)}</span>
              {l.tier && (
                <Badge variant="outline" className="text-[9px]">
                  {l.tier.toUpperCase().startsWith("A") ? "ممتاز" : l.tier.toUpperCase().startsWith("B") ? "جيد" : "عادي"}
                </Badge>
              )}
            </div>
          ) : (
            "—"
          )}
        </td>
        <td>
          <Badge
            variant={l.stage === "ACCEPTED" ? "success" : l.stage === "REVIEW" ? "warn" : "danger"}
          >
            <StatusDot status={l.stage} />
            {l.stage === "ACCEPTED" ? "مقبول" : l.stage === "REVIEW" ? "مراجعة" : "مرفوض"}
          </Badge>
        </td>
        <td>
          <button
            onClick={onOpenDrawer}
            className="p-1 rounded hover:bg-[var(--bg-hover)] text-[var(--fg-soft)]"
            title="عرض التفاصيل"
          >
            <ChevronDown className="h-4 w-4 -rotate-90" />
          </button>
        </td>
      </tr>
  );
}

function Detail({ label, value, ltr }: { label: string; value?: string | null; ltr?: boolean }) {
  return (
    <div className="rounded-lg border border-[var(--border-soft)] bg-[var(--bg-elev)] p-2.5">
      <div className="text-[10px] text-[var(--fg-soft)] mb-0.5">{label}</div>
      <div className={cn("font-medium truncate", ltr && "dir-ltr text-left")} dir={ltr ? "ltr" : undefined}>
        {value || "—"}
      </div>
    </div>
  );
}

function LeadPitchTab({ lead }: { lead: LeadRow }) {
  const [pitch, setPitch] = useState<PitchData | null>(null);
  const [loading, setLoading] = useState(false);
  const [copiedSubject, setCopiedSubject] = useState(false);
  const [copiedBody, setCopiedBody] = useState(false);
  const [copiedWa, setCopiedWa] = useState(false);
  const [angle, setAngle] = useState("زيادة الإيرادات واكتساب عملاء جدد مؤهلين");
  const [operatorPhone, setOperatorPhone] = useState(() => localStorage.getItem("leadEngine.operatorPhone") || "");
  const [editingPhone, setEditingPhone] = useState(false);
  const [tempPhone, setTempPhone] = useState("");

  const generate = async () => {
    setLoading(true);
    try {
      let res: PitchData;
      if (lead.lead_id) {
        try {
          res = await apiPitch.generateForLead(lead.lead_id);
        } catch {
          res = await apiPitch.generate({
            lead_id: lead.lead_id,
            name: lead.name,
            city: lead.city,
            domain: lead.domain,
            website: lead.website,
            decision_maker: lead.decision_maker,
            offer: angle,
          });
        }
      } else {
        res = await apiPitch.generate({
          name: lead.name,
          city: lead.city,
          domain: lead.domain,
          website: lead.website,
          decision_maker: lead.decision_maker,
          offer: angle,
        });
      }
      setPitch(res);
      toast.success("تم توليد رسائل العرض بنجاح عبر الذكاء الاصطناعي!");
    } catch (e: any) {
      toast.error("تعذر توليد العرض: " + (e.message || "خطأ غير متوقع"));
    } finally {
      setLoading(false);
    }
  };

  const copyText = (text: string, type: "subject" | "body" | "wa") => {
    navigator.clipboard.writeText(text);
    if (type === "subject") {
      setCopiedSubject(true);
      setTimeout(() => setCopiedSubject(false), 2000);
    } else if (type === "body") {
      setCopiedBody(true);
      setTimeout(() => setCopiedBody(false), 2000);
    } else {
      setCopiedWa(true);
      setTimeout(() => setCopiedWa(false), 2000);
    }
    toast.success("تم النسخ للحافظة");
  };

  const waUrl = useMemo(() => {
    if (!lead.phone) return null;
    let digits = lead.phone.replace(/[^0-9]/g, "");
    if (digits.startsWith("00")) digits = digits.substring(2);
    if (!digits || digits.length < 7) return null;
    const text = pitch?.whatsapp_message || `السلام عليكم ورحمة الله، بخصوص خدمات ${lead.name || "المنشأة"} الكريمة.. حاب أستفسر من حضرتكم`;
    return `https://wa.me/${digits}?text=${encodeURIComponent(text)}`;
  }, [lead.phone, lead.name, pitch]);

  const operatorWaUrl = useMemo(() => {
    if (!operatorPhone || !pitch) return null;
    let digits = operatorPhone.replace(/[^0-9]/g, "");
    if (digits.startsWith("00")) digits = digits.substring(2);
    if (!digits || digits.length < 7) return null;
    const msg = `[معاينة تجريبية لمسؤول الحملة - ${lead.name || "المنشأة"}]\n\n${pitch.whatsapp_message}`;
    return `https://wa.me/${digits}?text=${encodeURIComponent(msg)}`;
  }, [operatorPhone, lead.name, pitch]);

  return (
    <div className="space-y-4">
      {/* Configuration & Trigger */}
      <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-soft)] p-3.5 space-y-3">
        <div className="flex items-center justify-between">
          <div className="text-xs font-semibold text-[var(--fg)] flex items-center gap-1.5">
            <Sparkles className="h-3.5 w-3.5 text-amber-400" />
            توليد العرض الترويجي المخصص
          </div>
          <Badge variant="outline" className="text-[10px]">مخصص لجمهورك المستهدف</Badge>
        </div>
        <div className="space-y-1.5">
          <label className="text-[11px] text-[var(--fg-muted)] block">الزاوية التسويقية / عرض القيمة:</label>
          <div className="flex items-center gap-1 flex-wrap mb-1">
            {[
              { label: "🚀 اكتساب عملاء مؤهلين", value: "زيادة الإيرادات واكتساب عملاء جدد مؤهلين" },
              { label: "📉 تسريع إغلاق الصفقات", value: "تقليل دورة المبيعات وتأكيد الاجتماعات بجودة عالية" },
              { label: "⚡ أتمتة المتابعة الفورية", value: "أتمتة المتابعة والتفاعل السريع عبر قنوات التواصل" },
            ].map((p, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => setAngle(p.value)}
                className={cn(
                  "text-[10px] px-2 py-0.5 rounded-full border transition-all",
                  angle === p.value
                    ? "bg-amber-500/20 text-amber-300 border-amber-500/40 font-semibold"
                    : "bg-[var(--bg-elev)] text-[var(--fg-muted)] border-[var(--border-soft)] hover:border-[var(--border)]"
                )}
              >
                {p.label}
              </button>
            ))}
          </div>
          <Select
            value={angle}
            onChange={(e) => setAngle(e.target.value)}
            className="text-xs"
          >
            <option value="زيادة الإيرادات واكتساب عملاء جدد مؤهلين">زيادة الإيرادات واكتساب عملاء جدد مؤهلين</option>
            <option value="تقليل دورة المبيعات وتأكيد الاجتماعات بجودة عالية">تقليل دورة المبيعات وتأكيد الاجتماعات بجودة عالية</option>
            <option value="أتمتة المتابعة والتفاعل السريع عبر قنوات التواصل">أتمتة المتابعة والتفاعل السريع عبر قنوات التواصل</option>
            <option value="بناء شراكات تجارية B2B طويلة الأجل">بناء شراكات تجارية B2B طويلة الأجل</option>
          </Select>
        </div>
        <Button
          variant="primary"
          className="w-full text-xs py-2"
          onClick={generate}
          disabled={loading}
        >
          {loading ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              جارٍ تحليل النشاط وصياغة العرض…
            </>
          ) : (
            <>
              <Sparkles className="h-3.5 w-3.5" />
              {pitch ? "إعادة صياغة العرض بالذكاء الاصطناعي" : "توليد العرض ورسائل التواصل الآن"}
            </>
          )}
        </Button>
      </div>

      {pitch ? (
        <div className="space-y-4 animate-fade-in">
          {/* Hook / Icebreaker */}
          {pitch.hook && (
            <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
              <div className="text-[11px] font-semibold text-amber-400 mb-1 flex items-center gap-1">
                <Sparkles className="h-3 w-3" />
                المدخل الافتتاحي المقترح (Icebreaker Hook)
              </div>
              <p className="text-xs text-[var(--fg-soft)] leading-relaxed">
                "{pitch.hook}"
              </p>
            </div>
          )}

          {/* Pain Points */}
          {pitch.pain_points && pitch.pain_points.length > 0 && (
            <div className="rounded-lg border border-[var(--border-soft)] bg-[var(--bg-soft)] p-3">
              <div className="text-[11px] font-semibold text-[var(--fg-soft)] mb-1.5">
                تحديات مستهدفة تم رصدها للمنشأة:
              </div>
              <div className="flex flex-wrap gap-1.5">
                {pitch.pain_points.map((p, idx) => (
                  <Badge key={idx} variant="outline" className="text-[10px] bg-[var(--bg-elev)]">
                    • {p}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {/* WhatsApp Pitch */}
          <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-3.5 space-y-2.5">
            <div className="flex items-center justify-between">
              <div className="text-xs font-semibold text-emerald-400 flex items-center gap-1.5">
                <MessageCircle className="h-3.5 w-3.5" />
                رسالة واتساب مخصصة (WhatsApp Outreach)
              </div>
              <button
                onClick={() => copyText(pitch.whatsapp_message, "wa")}
                className="text-[11px] flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/25 transition-colors"
                title="نسخ الرسالة"
              >
                {copiedWa ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
                {copiedWa ? "تم النسخ" : "نسخ النص"}
              </button>
            </div>
            <div className="rounded-lg bg-[var(--bg-elev)] p-2.5 text-xs text-[var(--fg)] whitespace-pre-wrap font-mono leading-relaxed border border-emerald-500/20">
              {pitch.whatsapp_message}
            </div>
            {waUrl ? (
              <a
                href={waUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white transition-colors shadow-xs"
              >
                <MessageCircle className="h-4 w-4" />
                فتح في واتساب فوراً مع الرسالة
              </a>
            ) : (
              <div className="text-[11px] text-[var(--fg-muted)] text-center">
                (لا يتوفر رقم هاتف لإطلاق واتساب تلقائياً، يمكنك نسخ النص والتواصل يدوياً)
              </div>
            )}

            {/* Operator Preview on Personal WhatsApp */}
            <div className="pt-2 mt-1 border-t border-emerald-500/20">
              <div className="flex items-center justify-between text-[11px] mb-1.5">
                <span className="font-semibold text-emerald-300 flex items-center gap-1">
                  🧪 تجربة على رقمك الشخصي:
                </span>
                {operatorPhone && (
                  <button
                    onClick={() => {
                      setTempPhone(operatorPhone);
                      setEditingPhone(true);
                    }}
                    className="text-[10px] text-[var(--accent)] hover:underline"
                  >
                    تغيير رقمي ({operatorPhone})
                  </button>
                )}
              </div>
              {operatorPhone && !editingPhone ? (
                <a
                  href={operatorWaUrl || "#"}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="w-full flex items-center justify-center gap-2 py-1.5 px-3 rounded-lg text-xs font-medium bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/25 border border-emerald-500/30 transition-colors"
                  title="أرسل هذه الرسالة لرقمك الشخصي لتراها كما ستصل للعميل"
                >
                  <MessageCircle className="h-3.5 w-3.5" />
                  معاينة على رقمي في واتساب
                </a>
              ) : (
                <div className="flex items-center gap-1.5">
                  <Input
                    placeholder="رقمك لتجربة الرسائل (05xxxxxxxx)…"
                    value={tempPhone}
                    onChange={(e) => setTempPhone(e.target.value)}
                    className="text-xs h-7.5"
                    dir="ltr"
                  />
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      if (!tempPhone.trim()) return;
                      setOperatorPhone(tempPhone.trim());
                      localStorage.setItem("leadEngine.operatorPhone", tempPhone.trim());
                      setEditingPhone(false);
                      toast.success("تم حفظ رقمك للتجربة المباشرة");
                    }}
                    className="text-xs h-7.5 shrink-0"
                  >
                    حفظ
                  </Button>
                  {operatorPhone && (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setEditingPhone(false)}
                      className="text-xs h-7.5"
                    >
                      إلغاء
                    </Button>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Cold Email Pitch */}
          <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-soft)] p-3.5 space-y-2.5">
            <div className="flex items-center justify-between">
              <div className="text-xs font-semibold text-[var(--fg)] flex items-center gap-1.5">
                <Mail className="h-3.5 w-3.5 text-[var(--accent)]" />
                البريد الإلكتروني البارد (Cold Email)
              </div>
            </div>

            {/* Subject */}
            <div>
              <div className="flex items-center justify-between text-[11px] text-[var(--fg-muted)] mb-1">
                <span>عنوان الإيميل (Subject):</span>
                <button
                  onClick={() => copyText(pitch.cold_email_subject, "subject")}
                  className="flex items-center gap-1 text-[var(--accent)] hover:underline"
                >
                  {copiedSubject ? <Check className="h-2.5 w-2.5" /> : <Copy className="h-2.5 w-2.5" />}
                  {copiedSubject ? "تم النسخ" : "نسخ"}
                </button>
              </div>
              <div className="rounded-lg bg-[var(--bg-elev)] px-2.5 py-1.5 text-xs font-medium text-[var(--fg)] border border-[var(--border-soft)] truncate">
                {pitch.cold_email_subject}
              </div>
            </div>

            {/* Body */}
            <div>
              <div className="flex items-center justify-between text-[11px] text-[var(--fg-muted)] mb-1">
                <span>نص الإيميل:</span>
                <button
                  onClick={() => copyText(pitch.cold_email_body, "body")}
                  className="flex items-center gap-1 text-[var(--accent)] hover:underline"
                >
                  {copiedBody ? <Check className="h-2.5 w-2.5" /> : <Copy className="h-2.5 w-2.5" />}
                  {copiedBody ? "تم النسخ" : "نسخ النص"}
                </button>
              </div>
              <div className="rounded-lg bg-[var(--bg-elev)] p-2.5 text-xs text-[var(--fg)] whitespace-pre-wrap leading-relaxed border border-[var(--border-soft)] max-h-56 overflow-y-auto">
                {pitch.cold_email_body}
              </div>
            </div>

            {lead.email && (
              <a
                href={`mailto:${lead.email}?subject=${encodeURIComponent(pitch.cold_email_subject)}&body=${encodeURIComponent(pitch.cold_email_body)}`}
                className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-lg text-xs font-semibold bg-[var(--accent)] hover:opacity-90 text-white transition-opacity"
              >
                <Mail className="h-4 w-4" />
                فتح تطبيق البريد الإلكتروني
              </a>
            )}
          </div>
        </div>
      ) : (
        <div className="py-8 text-center text-xs text-[var(--fg-muted)] border border-dashed border-[var(--border)] rounded-xl">
          <Sparkles className="h-8 w-8 text-[var(--fg-soft)] mx-auto mb-2 opacity-50" />
          اضغط على زر التوليد أعلاه لصياغة رسالة بريد بارد وواتساب مخصصة فوراً لهذه المنشأة
        </div>
      )}
    </div>
  );
}

function LeadDrawer({ lead, onClose }: { lead: LeadRow; onClose: () => void }) {
  const l = lead;
  const [activeTab, setActiveTab] = useState<"details" | "pitch" | "audit">("details");
  const waUrl = getWhatsAppUrl(l.phone, l.name);

  return (
    <>
      <div className="fixed inset-0 bg-black/50 z-40 animate-fade-in" onClick={onClose} />
      <aside
        className="fixed inset-y-0 left-0 w-full max-w-lg bg-[var(--bg-elev)] border-e border-[var(--border)] shadow-[var(--shadow-lg)] z-50 overflow-y-auto animate-slide-up flex flex-col"
        dir="rtl"
      >
        {/* Sticky Header */}
        <div className="sticky top-0 bg-[var(--bg-elev)] border-b border-[var(--border)] px-5 py-4 z-10">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="text-[16px] font-bold truncate flex items-center gap-2">
                <Building2 className="h-4.5 w-4.5 text-[var(--accent)] shrink-0" />
                {l.name || "—"}
              </div>
              <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                <Badge variant={l.stage === "ACCEPTED" ? "success" : l.stage === "REVIEW" ? "warn" : "danger"} className="text-[10px]">
                  {l.stage === "ACCEPTED" ? "مقبول" : l.stage === "REVIEW" ? "مراجعة" : "مرفوض"}
                </Badge>
                {l.score != null && (
                  <span className="text-[12px] tnum font-bold">
                    الدرجة {l.score.toFixed(0)}
                    {l.tier && <span className="text-[var(--fg-soft)] font-medium"> · {l.tier.toUpperCase().startsWith("A") ? "ممتاز" : l.tier.toUpperCase().startsWith("B") ? "جيد" : "عادي"}</span>}
                  </span>
                )}
              </div>
            </div>
            <button onClick={onClose} className="p-1.5 rounded-lg text-[var(--fg-muted)] hover:bg-[var(--bg-hover)] hover:text-[var(--fg)] transition-colors" title="إغلاق">
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Modern Tabs */}
          <div className="flex items-center gap-1 mt-4 p-1 rounded-xl bg-[var(--bg-soft)] border border-[var(--border-soft)]">
            <button
              onClick={() => setActiveTab("details")}
              className={cn(
                "flex-1 py-1.5 px-3 rounded-lg text-xs font-medium transition-all flex items-center justify-center gap-1.5",
                activeTab === "details"
                  ? "bg-[var(--bg-elev)] text-[var(--fg)] shadow-xs font-semibold"
                  : "text-[var(--fg-muted)] hover:text-[var(--fg)]"
              )}
            >
              <Building2 className="h-3.5 w-3.5" />
              التفاصيل
            </button>
            <button
              onClick={() => setActiveTab("pitch")}
              className={cn(
                "flex-1 py-1.5 px-3 rounded-lg text-xs font-medium transition-all flex items-center justify-center gap-1.5",
                activeTab === "pitch"
                  ? "bg-[var(--bg-elev)] text-amber-400 shadow-xs font-semibold"
                  : "text-[var(--fg-muted)] hover:text-[var(--fg)]"
              )}
            >
              <Sparkles className="h-3.5 w-3.5 text-amber-400" />
              صياغة العرض (AI)
            </button>
            <button
              onClick={() => setActiveTab("audit")}
              className={cn(
                "flex-1 py-1.5 px-3 rounded-lg text-xs font-medium transition-all flex items-center justify-center gap-1.5",
                activeTab === "audit"
                  ? "bg-[var(--bg-elev)] text-[var(--accent)] shadow-xs font-semibold"
                  : "text-[var(--fg-muted)] hover:text-[var(--fg)]"
              )}
            >
              <ShieldCheck className="h-3.5 w-3.5" />
              سجل الأدلة والتقييم
            </button>
          </div>
        </div>

        {/* Tab Content */}
        <div className="p-5 space-y-5 flex-1">
          {activeTab === "details" && (
            <div className="space-y-5">
              {/* Quick Actions */}
              <div className="grid grid-cols-2 gap-2">
                {waUrl && (
                  <a
                    href={waUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white transition-colors shadow-xs"
                  >
                    <MessageCircle className="h-3.5 w-3.5" />
                    محادثة واتساب
                  </a>
                )}
                {l.email && (
                  <a
                    href={`mailto:${l.email}`}
                    className={cn(
                      "flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg text-xs font-semibold bg-[var(--accent)] hover:opacity-90 text-white transition-opacity shadow-xs",
                      !waUrl && "col-span-2"
                    )}
                  >
                    <Mail className="h-3.5 w-3.5" />
                    مراسلة بالبريد
                  </a>
                )}
              </div>

              <section>
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-[12px] font-semibold text-[var(--fg-soft)]">التواصل والحسابات</h3>
                  <SocialBadges social={l.social} linkedin={l.linkedin} />
                </div>
                <div className="space-y-1.5">
                  <DrawerRow icon={<Mail className="h-3.5 w-3.5" />} label="البريد" value={l.email} ltr
                    href={l.email ? `mailto:${l.email}` : undefined} />
                  <DrawerRow icon={<Phone className="h-3.5 w-3.5" />} label="الهاتف" value={l.phone} ltr
                    href={l.phone ? `tel:${l.phone}` : undefined} />
                  <DrawerRow icon={<Globe className="h-3.5 w-3.5" />} label="الموقع" value={l.website || l.domain} ltr
                    href={l.domain ? `https://${l.domain}` : undefined} />
                </div>
              </section>

              <section>
                <h3 className="text-[12px] font-semibold text-[var(--fg-soft)] mb-2">تفاصيل الشركة</h3>
                <div className="space-y-1.5">
                  <DrawerRow icon={<Building2 className="h-3.5 w-3.5" />} label="المدينة" value={l.city} />
                  <DrawerRow icon={<User className="h-3.5 w-3.5" />} label="صانع القرار" value={l.decision_maker} />
                  <DrawerRow icon={<CheckCircle2 className="h-3.5 w-3.5" />} label="حالة البريد"
                    value={l.email_status === "DELIVERABLE" ? "صالح" : l.email_status === "INVALID" ? "غير صالح" : l.email_status ? "محتاج مراجعة" : undefined} />
                  <DrawerRow icon={<ShieldCheck className="h-3.5 w-3.5" />} label="القوانين"
                    value={l.legal_status === "ALLOWED" ? "مسموح" : l.legal_status === "BLOCKED" ? "محجوب" : "خلال الحدود المسموحة"} />
                </div>
              </section>

              <section>
                <h3 className="text-[12px] font-semibold text-[var(--fg-soft)] mb-2">المصدر</h3>
                <div className="space-y-1.5">
                  <DrawerRow icon={<Briefcase className="h-3.5 w-3.5" />} label="الحملة"
                    value={l.job_id ? (ICP_LABELS[l.job_id] ?? "حملة توليد عملاء") : undefined} />
                </div>
              </section>
            </div>
          )}

          {activeTab === "pitch" && (
            <LeadPitchTab lead={l} />
          )}

          {activeTab === "audit" && (
            <div>
              {l.lead_id ? (
                <ReviewPanel leadId={l.lead_id} />
              ) : (
                <div className="py-8 text-center text-xs text-[var(--fg-muted)]">
                  لا يتوفر معرف للعميل لعرض سجل الأدلة
                </div>
              )}
            </div>
          )}
        </div>
      </aside>
    </>
  );
}

function DrawerRow({ icon, label, value, ltr, href }: {
  icon: React.ReactNode;
  label: string;
  value?: string | null;
  ltr?: boolean;
  href?: string;
}) {
  return (
    <div className="flex items-center gap-2.5 rounded-lg border border-[var(--border-soft)] bg-[var(--bg-soft)] px-3 py-2">
      <span className="text-[var(--fg-soft)] shrink-0">{icon}</span>
      <span className="text-[12px] text-[var(--fg-muted)] shrink-0">{label}</span>
      <span className="ms-auto text-[13px] font-medium truncate" dir={ltr ? "ltr" : undefined}>
        {href && value ? (
          <a href={href} target={href.startsWith("http") ? "_blank" : undefined} rel="noopener"
            className="text-[var(--accent)] hover:underline">{value}</a>
        ) : (value || "—")}
      </span>
    </div>
  );
}
