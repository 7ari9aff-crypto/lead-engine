import { useEffect, useMemo, useState } from "react";
import {
  Settings, Save, RotateCcw, FileCode, Check, Search, SlidersHorizontal,
  Target, Scale, Timer,
} from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { apiGet, apiPost } from "@/lib/api";
import { toast } from "sonner";
import { Spinner } from "@/components/ui/EmptyState";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/layout/PageHeader";

const FILE_META: Record<string, { label: string; desc: string; icon: any }> = {
  settings: { label: "الإعدادات العامة", desc: "الروتر، التبريد، الدرجات، أوزان التقييم", icon: SlidersHorizontal },
  cache_policy: { label: "سياسة الكاش", desc: "مدة الاحتفاظ لكل نوع بيانات بالأيام", icon: Timer },
  icp_v0_saudi_dental: { label: "ملف الـICP", desc: "المدن والكلمات المفتاحية ومعايير التأهيل", icon: Target },
  legal_sa: { label: "سياسة نظام البيانات السعودي", desc: "أنواع البيانات المسموحة والاحتفاظ", icon: Scale },
};

export function ConfigPage() {
  const [files, setFiles] = useState<{ path: string; content: string; key: string }[]>([]);
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState("");

  useEffect(() => {
    apiGet
      .config()
      .then((r) => {
        const list = (r.files || []).map((f, i) => ({
          ...f,
          key: f.path.includes("settings") ? "settings" :
               f.path.includes("cache_policy") ? "cache_policy" :
               f.path.includes("icp") ? "icp_v0_saudi_dental" :
               f.path.includes("legal") && f.path.includes("sa") ? "legal_sa" :
               f.path.includes("legal") ? "legal_default" : `file_${i}`,
        }));
        setFiles(list);
        if (list[0]) {
          setActiveKey(list[0].key);
          setDraft(list[0].content);
        }
      })
      .catch((e) => toast.error("فشل جلب الإعدادات: " + e.message))
      .finally(() => setLoading(false));
  }, []);

  const active = files.find((f) => f.key === activeKey) ?? null;
  const dirty = active ? draft !== active.content : false;

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return files;
    return files.filter((f) =>
      (FILE_META[f.key]?.label ?? f.key).toLowerCase().includes(q) || f.path.includes(q));
  }, [files, search]);

  function select(f: { key: string; content: string }) {
    if (dirty && !confirm("فيه تعديلات غير محفوظة — تبديل الملف هيفقدها. تكمل؟")) return;
    setActiveKey(f.key);
    setDraft(f.content);
  }

  async function save() {
    if (!active) return;
    setSaving(true);
    try {
      const r = await apiPost.saveConfig(active.key, draft);
      setFiles((fs) => fs.map((f) => (f.key === active.key ? { ...f, content: draft } : f)));
      toast.success(`تم الحفظ — نسخة احتياطية عند ${r.backup}`);
    } catch (e: any) {
      toast.error(e.message || "فشل الحفظ — لو على سيرفر سيرفرليس عدّل من الإعدادات البيئية");
    } finally {
      setSaving(false);
    }
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        if (dirty && !saving) save();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner className="h-6 w-6 text-[var(--accent)]" />
      </div>
    );
  }

  const lines = draft ? draft.split("\n").length : 0;

  return (
    <div className="space-y-5">
      <PageHeader
        icon={<Settings className="h-4 w-4 text-white" />}
        title="الإعدادات"
        description="ملفات النظام الأربعة بتحكم مباشر — كل حفظ يعمل نسخة احتياطية تلقائيًا، والسيرفر يتحقق من صحة YAML"
        action={
          dirty && active ? (
            <div className="flex gap-2">
              <Button variant="ghost" size="sm" onClick={() => setDraft(active.content)}>
                <RotateCcw className="h-3.5 w-3.5" />
                تراجع
              </Button>
              <Button variant="primary" size="sm" onClick={save} loading={saving}>
                <Save className="h-3.5 w-3.5" />
                حفظ التغييرات
              </Button>
            </div>
          ) : undefined
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-4 items-start">
        {/* File list */}
        <Card className="p-2 space-y-1">
          <div className="relative mb-1">
            <Search className="absolute right-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-[var(--fg-soft)] pointer-events-none" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="ابحث في الملفات…"
              className="w-full h-8.5 py-1.5 rounded-lg border border-[var(--border)] bg-[var(--bg-soft)] pr-9 pl-3 text-[13px] focus:outline-none focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--ring)]"
            />
          </div>
          {filtered.map((f) => {
            const meta = FILE_META[f.key];
            const Icon = meta?.icon ?? FileCode;
            const isActive = f.key === activeKey;
            return (
              <button
                key={f.key}
                onClick={() => select(f)}
                className={cn(
                  "w-full text-right rounded-lg px-3 py-2.5 transition-colors flex items-start gap-2.5",
                  isActive ? "bg-[var(--accent-soft)]" : "hover:bg-[var(--bg-hover)]"
                )}
              >
                <Icon className={cn("h-4 w-4 mt-0.5 shrink-0", isActive ? "text-[var(--accent)]" : "text-[var(--fg-soft)]")} />
                <span className="min-w-0">
                  <span className={cn("block text-[13px] font-medium truncate", isActive ? "text-[var(--accent-hover)]" : "text-[var(--fg)]")}>
                    {meta?.label ?? f.key}
                  </span>
                  <span className="block text-[10px] text-[var(--fg-soft)] truncate mt-0.5" dir="ltr">{f.path}</span>
                </span>
              </button>
            );
          })}
        </Card>

        {/* Editor */}
        <Card className="p-0 overflow-hidden">
          <div className="flex items-center gap-2.5 px-4 h-11 border-b border-[var(--border)] bg-[var(--bg-soft)]">
            <FileCode className="h-4 w-4 text-[var(--accent)] shrink-0" />
            <span className="text-[13px] font-semibold">{FILE_META[active?.key ?? ""]?.label ?? active?.key}</span>
            <span className="text-[10px] text-[var(--fg-soft)] font-mono truncate hidden sm:inline" dir="ltr">{active?.path}</span>
            <span className="ms-auto flex items-center gap-2 shrink-0">
              {dirty ? (
                <Badge variant="warn" className="text-[10px]">تعديلات غير محفوظة</Badge>
              ) : (
                <Badge variant="success" className="text-[10px]">
                  <Check className="h-3 w-3" />
                  محفوظ
                </Badge>
              )}
              <span className="text-[10px] text-[var(--fg-soft)] tnum hidden md:inline">{lines} سطر</span>
            </span>
          </div>
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            spellCheck={false}
            dir="ltr"
            className="w-full min-h-[420px] bg-[var(--bg-elev)] text-[12.5px] leading-6 font-mono p-4 focus:outline-none resize-y text-[var(--fg)]"
          />
          <div className="flex items-center justify-between px-4 h-9 border-t border-[var(--border)] bg-[var(--bg-soft)] text-[10px] text-[var(--fg-soft)]">
            <span>YAML — السيرفر يتحقق من الصيغة قبل الحفظ ويرفض أي ملف غير صالح</span>
            <span className="font-mono hidden sm:inline">Ctrl S للحفظ</span>
          </div>
        </Card>
      </div>
    </div>
  );
}
