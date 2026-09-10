import { useEffect, useState } from "react";
import {
  Settings,
  Save,
  RotateCcw,
  FileCode,
  CheckCircle2,
  AlertCircle,
  Search,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Input, Textarea } from "@/components/ui/Input";
import { apiGet, apiPost } from "@/lib/api";
import { toast } from "sonner";
import { Spinner } from "@/components/ui/EmptyState";
import { cn } from "@/lib/utils";

export function ConfigPage() {
  const [files, setFiles] = useState<{ path: string; content: string; key: string }[]>([]);
  const [active, setActive] = useState<{ key: string; path: string } | null>(null);
  const [content, setContent] = useState("");
  const [original, setOriginal] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState("");

  useEffect(() => {
    apiGet
      .config()
      .then((r) => {
        const list = (r.files || []).map((f, i) => ({
          ...f,
          // infer key from path
          key: f.path.includes("settings") ? "settings" :
               f.path.includes("cache_policy") ? "cache_policy" :
               f.path.includes("icp") ? "icp_v0_saudi_dental" :
               f.path.includes("legal") && f.path.includes("sa") ? "legal_sa" :
               f.path.includes("legal") ? "legal_default" : `file_${i}`,
        }));
        setFiles(list);
        if (list[0]) {
          setActive({ key: list[0].key, path: list[0].path });
          setContent(list[0].content);
          setOriginal(list[0].content);
        }
      })
      .catch((e) => toast.error("فشل جلب الإعدادات: " + e.message))
      .finally(() => setLoading(false));
  }, []);

  function selectFile(f: { key: string; path: string }) {
    const file = files.find((x) => x.key === f.key);
    if (file) {
      setActive(f);
      setContent(file.content);
      setOriginal(file.content);
    }
  }

  async function save() {
    if (!active) return;
    if (content === original) {
      toast.info("لا تغييرات للحفظ");
      return;
    }
    setSaving(true);
    try {
      await apiPost.saveConfig(active.key, content);
      toast.success(`تم حفظ ${active.path} — يدخل حيّز التنفيذ من التشغيل القادم`);
      setOriginal(content);
      setFiles((prev) => prev.map((f) => (f.key === active.key ? { ...f, content } : f)));
    } catch (e: any) {
      toast.error("فشل: " + e.message);
    } finally {
      setSaving(false);
    }
  }

  function revert() {
    setContent(original);
    toast.info("تم التراجع");
  }

  const filteredFiles = files.filter((f) => !search || f.path.toLowerCase().includes(search.toLowerCase()));
  const dirty = content !== original;
  const fileName = active?.path.split("/").pop() || active?.path || "";
  const yamlValid = !content.includes("\t");

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Settings className="h-5 w-5 text-[var(--accent)]" />
            الإعدادات
          </h1>
          <p className="text-sm text-[var(--fg-muted)] mt-1">
            أي تعديل يطبق من التشغيل القادم، ويُعمل منه نسخة احتياطية <code>.bak</code> تلقائيًا.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" onClick={revert} disabled={!dirty}>
            <RotateCcw className="h-4 w-4" />
            تراجع
          </Button>
          <Button variant="primary" onClick={save} disabled={!dirty || !yamlValid} loading={saving}>
            <Save className="h-4 w-4" />
            حفظ
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Spinner className="h-8 w-8 text-[var(--accent)]" />
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">الملفات</CardTitle>
            </CardHeader>
            <CardContent className="p-2">
              <div className="relative mb-2">
                <Search className="absolute right-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-[var(--fg-soft)]" />
                <Input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="ابحث…"
                  className="h-8 pe-9 text-xs"
                />
              </div>
              <div className="space-y-1">
                {filteredFiles.map((f) => {
                  const name = f.path.split("/").pop() || f.path;
                  return (
                    <button
                      key={f.key}
                      onClick={() => selectFile({ key: f.key, path: f.path })}
                      className={cn(
                        "w-full text-right rounded-lg px-3 py-2 text-xs flex items-center gap-2 transition-colors",
                        active?.key === f.key
                          ? "bg-[var(--accent-soft)] text-[var(--accent-hover)]"
                          : "text-[var(--fg-muted)] hover:bg-[var(--bg-hover)]"
                      )}
                    >
                      <FileCode className="h-3.5 w-3.5 shrink-0" />
                      <div className="flex-1 min-w-0">
                        <div className="font-medium truncate">{name}</div>
                        <div className="text-[10px] text-[var(--fg-soft)] truncate" dir="ltr">
                          {f.path}
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div className="flex items-center justify-between gap-2">
                <div>
                  <CardTitle>
                    <FileCode className="h-4 w-4" />
                    {fileName}
                    {dirty && (
                      <Badge variant="warn" className="text-[10px]">
                        <AlertCircle className="h-3 w-3" />
                        غير محفوظ
                      </Badge>
                    )}
                  </CardTitle>
                  <CardDescription className="font-mono" dir="ltr">
                    {active?.path}
                  </CardDescription>
                </div>
                <div className="flex items-center gap-2">
                  {yamlValid ? (
                    <Badge variant="success" className="text-[10px]">
                      <CheckCircle2 className="h-3 w-3" />
                      YAML سليم
                    </Badge>
                  ) : (
                    <Badge variant="danger" className="text-[10px]">
                      <AlertCircle className="h-3 w-3" />
                      خطأ في التنسيق
                    </Badge>
                  )}
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <Textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                spellCheck={false}
                dir="ltr"
                className="font-mono text-xs min-h-[60vh] leading-relaxed"
              />
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
