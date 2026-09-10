import { useState } from "react";
import {
  Boxes,
  Power,
  PowerOff,
  RotateCcw,
  Activity,
  Search,
  Settings2,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge, StatusDot } from "@/components/ui/Badge";
import { Input } from "@/components/ui/Input";
import { useLiveData } from "@/hooks/useLiveData";
import { apiGet, apiPost, type ProviderRow } from "@/lib/api";
import { toast } from "sonner";
import { cn, formatNumber, relativeTime } from "@/lib/utils";
import { Spinner, EmptyState } from "@/components/ui/EmptyState";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/Dialog";
import { PageHeader } from "@/components/layout/PageHeader";
import { Label } from "@/components/ui/Input";

const STATUSES = ["ALL", "active", "degraded", "exhausted", "cooldown", "disabled"] as const;
const TASKS = ["ALL", "search", "reasoning", "enrichment", "verification", "embedding"] as const;

export function ProvidersPage() {
  const { data, loading, refresh } = useLiveData(() => apiGet.providers(), 5000);
  const [filter, setFilter] = useState<"ALL" | string>("ALL");
  const [taskFilter, setTaskFilter] = useState<"ALL" | string>("ALL");
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [editing, setEditing] = useState<ProviderRow | null>(null);
  const [baseUrl, setBaseUrl] = useState("");
  const [modelName, setModelName] = useState("");
  const [savingConfig, setSavingConfig] = useState(false);

  async function act(name: string, task: string, action: "enable" | "disable" | "reset") {
    setBusy(`${name}:${task}:${action}`);
    try {
      if (action === "enable") {
        await apiPost.providerSetStatus(name, task, "active");
        toast.success(`تم تفعيل ${name}`);
      } else if (action === "disable") {
        await apiPost.providerSetStatus(name, task, "disabled");
        toast.success(`تم تعطيل ${name}`);
      } else {
        await apiPost.providerReset(name, task);
        toast.success(`تم تصفير استهلاك ${name}`);
      }
      refresh();
    } catch (e: any) {
      toast.error("فشل: " + e.message);
    } finally {
      setBusy(null);
    }
  }

  function openConfig(provider: ProviderRow) {
    setEditing(provider);
    setBaseUrl(provider.base_url || "");
    setModelName(provider.model_name || "");
  }

  async function saveConfig() {
    if (!editing) return;
    setSavingConfig(true);
    try {
      await apiPost.providerConfig(editing.name, editing.task, { base_url: baseUrl, model_name: modelName });
      toast.success(`تم حفظ إعدادات ${editing.name}`);
      setEditing(null);
      refresh();
    } catch (e: any) {
      toast.error("فشل حفظ الإعدادات: " + e.message);
    } finally {
      setSavingConfig(false);
    }
  }

  const providers = data?.providers ?? [];
  const filtered = providers.filter((p) => {
    if (filter !== "ALL" && p.status !== filter) return false;
    if (taskFilter !== "ALL" && p.task !== taskFilter) return false;
    if (search && !`${p.name} ${p.task} ${p.env_key}`.toLowerCase().includes(search.toLowerCase()))
      return false;
    return true;
  });

  return (
    <div className="space-y-6">
      <PageHeader
        icon={<Boxes className="h-4 w-4 text-[var(--accent)]" />}
        title="المزوّدون"
        description="الحالة هنا مقروءة مباشرة من قاعدة البيانات — نفس اللي بياخدها الـRouter قراره."
      />

      {/* Filters */}
      <Card>
        <CardContent className="p-4 flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--fg-soft)]" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="ابحث باسم أو نوع…"
              className="pe-10"
            />
          </div>
          <div className="flex gap-1 flex-wrap">
            {STATUSES.map((s) => (
              <Button
                key={s}
                size="sm"
                variant={filter === s ? "primary" : "outline"}
                onClick={() => setFilter(s)}
              >
                {s === "ALL" ? "الكل" : s}
              </Button>
            ))}
          </div>
          <div className="flex gap-1 flex-wrap">
            {TASKS.map((t) => (
              <Button
                key={t}
                size="sm"
                variant="outline"
                onClick={() => setTaskFilter(t)}
                className={cn(taskFilter === t && "bg-[var(--accent-soft)] text-[var(--accent-hover)] border-[var(--accent)]")}
              >
                {t === "ALL" ? "كل المهام" : t}
              </Button>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          {loading && !data ? (
            <div className="flex items-center justify-center py-20">
              <Spinner className="h-6 w-6 text-[var(--accent)]" />
            </div>
          ) : filtered.length === 0 ? (
            <EmptyState
              icon={<Boxes className="h-8 w-8" />}
              title="لا يوجد مزوّدون"
              description="جرّب تغيير الفلاتر أو أضف مفاتيح API في تبويب المفاتيح"
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[var(--border)] bg-[var(--bg-soft)]">
                    <th className="text-right p-3 font-semibold">المزوّد</th>
                    <th className="text-right p-3 font-semibold">المهمة</th>
                    <th className="text-right p-3 font-semibold">الحالة</th>
                    <th className="text-right p-3 font-semibold">المفتاح</th>
                    <th className="text-right p-3 font-semibold">الاستهلاك</th>
                    <th className="text-right p-3 font-semibold">الاستدعاءات</th>
                    <th className="text-right p-3 font-semibold">آخر استخدام</th>
                    <th className="text-right p-3 font-semibold">إجراءات</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((p, i) => {
                    const usage = p.quota_limit ? ((p.quota_used || 0) / p.quota_limit) * 100 : 0;
                    const isBusy = busy === `${p.name}:${p.task}`;
                    return (
                      <tr key={i} className="border-b border-[var(--border-soft)] hover:bg-[var(--bg-hover)] transition-colors">
                        <td className="p-3 font-medium">
                          <div className="flex items-center gap-2">
                            <Activity className="h-3.5 w-3.5 text-[var(--accent)]" />
                            {p.name}
                          </div>
                        </td>
                        <td className="p-3">
                          <Badge variant="outline" className="text-[10px]">
                            {p.task}
                          </Badge>
                        </td>
                        <td className="p-3">
                          <Badge
                            variant={
                              p.status === "active"
                                ? "success"
                                : p.status === "degraded" || p.status === "exhausted"
                                ? "warn"
                                : "default"
                            }
                            className="text-[10px]"
                          >
                            <StatusDot status={p.status} />
                            {p.status}
                          </Badge>
                        </td>
                        <td className="p-3">
                          <Badge
                            variant={p.key_state === "set" ? "success" : p.key_state === "missing" ? "danger" : "default"}
                            className="text-[10px]"
                          >
                            {p.key_state === "set" ? "✔" : p.key_state === "missing" ? "✗" : p.key_state === "local" ? "محلي" : "?"}
                          </Badge>
                        </td>
                        <td className="p-3 tabular-nums" dir="ltr">
                          <div className="flex flex-col gap-1">
                            <span>
                              {formatNumber(p.quota_used || 0)} / {p.quota_limit ? formatNumber(p.quota_limit) : "∞"}
                            </span>
                            {p.quota_limit && (
                              <div className="h-1 w-24 rounded-full bg-[var(--bg-soft)] overflow-hidden">
                                <div
                                  className={cn(
                                    "h-full rounded-full transition-all",
                                    usage > 80 ? "bg-[var(--danger)]" :
                                    usage > 60 ? "bg-[var(--warn)]" :
                                    "bg-[var(--success)]"
                                  )}
                                  style={{ width: `${Math.min(100, usage)}%` }}
                                />
                              </div>
                            )}
                          </div>
                        </td>
                        <td className="p-3 tabular-nums">{formatNumber(p.calls || 0)}</td>
                        <td className="p-3 text-xs text-[var(--fg-muted)]">
                          {p.last_used ? relativeTime(p.last_used) : "—"}
                        </td>
                        <td className="p-3">
                          <div className="flex gap-1">
                            {p.status === "disabled" ? (
                              <Button
                                size="icon-sm"
                                variant="ghost"
                                disabled={isBusy}
                                onClick={() => act(p.name, p.task, "enable")}
                                title="تفعيل"
                              >
                                <Power className="h-3.5 w-3.5 text-[var(--success)]" />
                              </Button>
                            ) : (
                              <Button
                                size="icon-sm"
                                variant="ghost"
                                disabled={isBusy}
                                onClick={() => act(p.name, p.task, "disable")}
                                title="تعطيل"
                              >
                                <PowerOff className="h-3.5 w-3.5 text-[var(--warn)]" />
                              </Button>
                            )}
                            <Button
                              size="icon-sm"
                              variant="ghost"
                              disabled={isBusy}
                              onClick={() => act(p.name, p.task, "reset")}
                              title="تصفير الاستهلاك"
                            >
                              <RotateCcw className="h-3.5 w-3.5" />
                            </Button>
                            <Button
                              size="icon-sm"
                              variant="ghost"
                              disabled={isBusy}
                              onClick={() => openConfig(p)}
                              title="إعدادات المزود"
                            >
                              <Settings2 className="h-3.5 w-3.5" />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={Boolean(editing)} onOpenChange={(open) => !open && setEditing(null)}>
        <DialogContent dir="rtl">
          <DialogHeader>
            <DialogTitle>إعدادات {editing?.name}</DialogTitle>
            <DialogDescription>
              إعدادات غير سرية للمزود. المفتاح نفسه يُدار من صفحة مفاتيح API.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label htmlFor="provider-base-url">رابط المزود</Label>
              <Input id="provider-base-url" dir="ltr" value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} placeholder="https://api.provider.com" />
            </div>
            <div>
              <Label htmlFor="provider-model">اسم النموذج</Label>
              <Input id="provider-model" dir="ltr" value={modelName} onChange={(event) => setModelName(event.target.value)} placeholder="gemini-2.5-flash" />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="ghost" onClick={() => setEditing(null)}>إلغاء</Button>
              <Button variant="primary" onClick={saveConfig} loading={savingConfig}>حفظ الإعدادات</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
