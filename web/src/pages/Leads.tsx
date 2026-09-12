import { useState, useMemo, useCallback } from "react";
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
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge, StatusDot } from "@/components/ui/Badge";
import { Input, Select } from "@/components/ui/Input";
import { useLiveData } from "@/hooks/useLiveData";
import { apiGet, apiPost, type LeadRow } from "@/lib/api";
import { downloadFile, formatNumber, truncate, cn } from "@/lib/utils";
import { friendlyError, ICP_LABELS } from "@/lib/friendly";
import { Spinner, EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatCard } from "@/components/ui/FilterPills";
import { toast } from "sonner";

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

export function LeadsPage() {
  const { data, loading, refresh } = useLiveData(() => apiGet.leads({ limit: 500 }), 5000);
  const [search, setSearch] = useState("");
  const [stage, setStage] = useState("");
  const [jobId, setJobId] = useState("");
  const [saved, setSaved] = useState<SavedSearch[]>(loadSaved);
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveName, setSaveName] = useState("");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [drawerLead, setDrawerLead] = useState<LeadRow | null>(null);
  const [bulkBusy, setBulkBusy] = useState<string | null>(null);

  const leads = data ?? [];
  const jobs = Array.from(new Set(leads.map((l) => l.job_id).filter(Boolean))) as string[];

  const filtered = useMemo(() => {
    return leads.filter((l) => {
      if (stage && l.stage !== stage) return false;
      if (jobId && l.job_id !== jobId) return false;
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
  }, [leads, search, stage, jobId]);

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
  }

  const selectedRows = filtered.filter((_, i) => selected.has(i));

  function toggleAll() {
    if (selected.size === filtered.length) setSelected(new Set());
    else setSelected(new Set(filtered.map((_, i) => i)));
  }

  async function bulkVerify() {
    setBulkBusy("verify");
    let ok = 0, bad = 0;
    for (const l of selectedRows) {
      if (!l.email) continue;
      try {
        await apiPost.verifyEmail(l.email);
        ok += 1;
      } catch {
        bad += 1;
      }
    }
    setBulkBusy(null);
    toast.success(`تم فحص ${ok} إيميل${bad ? ` — وفشل ${bad}` : ""}، والنتائج بتتحدث في القايمة`);
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

  return (
    <div className="space-y-6">
      <PageHeader
        icon={<Database className="h-4 w-4 text-[var(--accent)]" />}
        title="العملاء المحتملون"
        description={`${formatNumber(stats.total)} إجمالي · ${formatNumber(stats.accepted)} مقبولة · ${formatNumber(stats.review)} مراجعة · ${formatNumber(stats.rejected)} مرفوضة`}
        action={
          <Button variant="primary" onClick={() => exportCSV(filtered)} disabled={filtered.length === 0}>
            <Download className="h-4 w-4" />
            تنزيل الملف ({filtered.length})
          </Button>
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
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative flex-1 min-w-[200px]">
              <Search className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--fg-soft)]" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="ابحث بالاسم، المدينة، الإيميل…"
                className="pe-10"
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
                  <button onClick={() => removeSaved(s.name)} title="حذف البحث المحفوظ" className="hover:text-[var(--danger)]">
                    <X className="h-3 w-3" />
                  </button>
                </span>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Bulk actions bar */}
      {selected.size > 0 && (
        <Card className="border-[var(--accent)]/50 animate-slide-up">
          <CardContent className="p-3 flex items-center gap-2 flex-wrap">
            <Badge variant="accent" className="text-[11px]">
              محدد: {selected.size} من {filtered.length}
            </Badge>
            <Button variant="outline" size="sm" disabled={bulkBusy != null} onClick={() => exportCSV(selectedRows, "_selected")}>
              <Download className="h-3.5 w-3.5" />
              تصدير المحدد
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={bulkBusy != null || !selectedRows.some((l) => l.email)}
              onClick={bulkVerify}
              title="فحص إيميلات العملاء المحددة واحدًا واحدًا"
            >
              {bulkBusy === "verify" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <MailCheck className="h-3.5 w-3.5" />}
              فحص المحدد
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="text-[var(--danger)]"
              disabled={bulkBusy != null || !selectedRows.some((l) => l.lead_id)}
              onClick={bulkDelete}
            >
              {bulkBusy === "delete" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
              حذف المحدد
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setSelected(new Set())} className="ms-auto">
              إلغاء التحديد
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          {loading && !data ? (
            <div className="flex items-center justify-center py-20">
              <Spinner className="h-6 w-6 text-[var(--accent)]" />
            </div>
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
                        checked={selected.size === filtered.length && filtered.length > 0}
                        onChange={toggleAll}
                        className="accent-[var(--accent)]"
                        title="تحديد الكل"
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
                      key={l.lead_id || i}
                      lead={l}
                      selected={selected.has(i)}
                      onToggleSelect={() => {
                        const next = new Set(selected);
                        if (next.has(i)) next.delete(i);
                        else next.add(i);
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
              {l.phone && (
                <span className="text-[10px] text-[var(--fg-muted)] flex items-center gap-1" dir="ltr">
                  <Phone className="h-3 w-3" /> {l.phone}
                </span>
              )}
            </span>
          </button>
        </td>
        <td className="text-xs">{l.city || "—"}</td>
        <td>
          {l.domain ? (
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
          ) : (
            "—"
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

function LeadDrawer({ lead, onClose }: { lead: LeadRow; onClose: () => void }) {
  const l = lead;
  return (
    <>
      <div className="fixed inset-0 bg-black/50 z-40 animate-fade-in" onClick={onClose} />
      <aside
        className="fixed inset-y-0 left-0 w-full max-w-md bg-[var(--bg-elev)] border-e border-[var(--border)] shadow-[var(--shadow-lg)] z-50 overflow-y-auto animate-slide-up"
        dir="rtl"
      >
        <div className="sticky top-0 bg-[var(--bg-elev)] border-b border-[var(--border)] px-5 py-4 flex items-start justify-between gap-3">
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

        <div className="p-5 space-y-5">
          <section>
            <h3 className="text-[12px] font-semibold text-[var(--fg-soft)] mb-2">التواصل</h3>
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

          {l.email && (
            <Button variant="primary" className="w-full" onClick={() => { window.location.href = `mailto:${l.email}`; }}>
              <Mail className="h-4 w-4" />
              راسلهم الآن
            </Button>
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
