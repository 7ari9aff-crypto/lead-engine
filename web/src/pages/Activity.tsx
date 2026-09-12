// TODO: wire /activity → <ActivityPage /> in web/src/App.tsx (parent orchestrator)

import { useState, useMemo } from "react";
import {
  Activity as ActivityIcon,
  RefreshCw,
  Bot,
  ShieldCheck,
  Clock,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { FilterPills } from "@/components/ui/FilterPills";
import { PageHeader } from "@/components/layout/PageHeader";
import { apiGet, type ActivityEvent } from "@/lib/api";
import { useLiveData } from "@/hooks/useLiveData";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { describePayload } from "@/lib/friendly";

type FilterMode = "all" | "job." | "agent." | "approval.";

const FILTERS: { value: FilterMode; label: string }[] = [
  { value: "all", label: "الكل" },
  { value: "job.", label: "المهام" },
  { value: "agent.", label: "الوكلاء" },
  { value: "approval.", label: "الموافقات" },
];

function iconForKind(kind: string) {
  if (kind.startsWith("agent.")) return <Bot className="h-4 w-4" />;
  if (kind.startsWith("approval.")) return <ShieldCheck className="h-4 w-4" />;
  if (kind.startsWith("job.")) return <ActivityIcon className="h-4 w-4" />;
  return <ActivityIcon className="h-4 w-4" />;
}

function toneForKind(kind: string): "info" | "accent" | "warn" | "default" {
  if (kind.startsWith("agent.")) return "accent";
  if (kind.startsWith("approval.")) return "warn";
  if (kind.startsWith("job.")) return "info";
  return "default";
}

const KIND_LABELS: Record<string, string> = {
  "job.started": "بدأت مهمة",
  "job.completed": "اكتملت مهمة",
  "job.paused": "توقفت مهمة مؤقتًا",
  "job.failed": "فشلت مهمة",
  "agent.started": "بدأ الوكيل",
  "agent.finished": "أنهى الوكيل",
  "agent.failed": "فشل الوكيل",
  "approval.requested": "طلب موافقة",
  "approval.approved": "تمت الموافقة",
  "approval.rejected": "تم الرفض",
  "lead.accepted": "قُبل عميل محتمل",
  "lead.rejected": "رُفض عميل محتمل",
};

function displayLabel(kind: string): string {
  return KIND_LABELS[kind] ?? kind.replace(/[._]/g, " ");
}

function summarizePayload(payload: any): string {
  if (!payload || typeof payload !== "object") return "";
  if (typeof payload === "string") { try { payload = JSON.parse(payload); } catch { return ""; } }
  const rows = describePayload(payload);
  if (!rows.length) return "";
  return rows.map((r) => `${r.label}: ${r.value}`).join(" · ");
}

function formatTs(ts: string): string {
  try {
    return new Date(ts).toLocaleString("ar-EG", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return ts;
  }
}

export function ActivityPage() {
  const [filter, setFilter] = useState<FilterMode>("all");
  // Backend only supports exact-kind matching via /api/activity?kind=...
  // For prefix filters we fetch a wider window and filter client-side.
  const fetchLimit = filter === "all" ? 50 : 200;

  const { data, loading, error, refresh } = useLiveData(
    () => apiGet.activity(fetchLimit, undefined),
    5000,
  );

  const events = useMemo<ActivityEvent[]>(() => {
    const raw = data?.events ?? [];
    if (filter === "all") return raw;
    return raw.filter((e) => e.kind?.startsWith(filter));
  }, [data, filter]);

  async function handleRefresh() {
    await refresh();
    if (error) toast.error("فشل تحديث السجل");
  }

  return (
    <div className="space-y-5">
      <PageHeader
        icon={<ActivityIcon className="h-4 w-4 text-white" />}
        title="سجل النشاط"
        description="آخر أحداث المنصة بالترتيب الزمني — مهام، تشغيل وكلاء، وموافقات"
        action={
          <Button
            variant="outline"
            size="sm"
            onClick={handleRefresh}
            disabled={loading}
          >
            <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
            تحديث
          </Button>
        }
      />

      <div className="flex items-center justify-between flex-wrap gap-3">
        <FilterPills
          options={FILTERS}
          value={filter}
          onChange={(v) => setFilter(v as FilterMode)}
        />
        <div className="text-xs text-[var(--fg-muted)]">
          {events.length} حدث
        </div>
      </div>

      <Card>
        <CardContent className="p-0">
          {loading && events.length === 0 ? (
            <div className="p-10 text-center text-sm text-[var(--fg-muted)]">
              جاري التحميل…
            </div>
          ) : events.length === 0 ? (
            <EmptyState
              icon={<ActivityIcon className="h-7 w-7" />}
              title="لا توجد أحداث"
              description="ستظهر هنا أحداث النظام فور تشغيل أول مهمة أو وكيل."
            />
          ) : (
            <ul className="divide-y divide-[var(--border-soft)]" dir="rtl">
              {events.map((ev) => (
                <li
                  key={ev.id}
                  className="flex items-start gap-3 px-5 py-3.5 hover:bg-[var(--bg-hover)] transition-colors"
                >
                  <div
                    className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg"
                    style={{
                      background: `color-mix(in srgb, var(--accent) 12%, transparent)`,
                      color: "var(--accent)",
                    }}
                  >
                    {iconForKind(ev.kind)}
                  </div>

                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Badge variant={toneForKind(ev.kind)} className="text-[10px]">
                        {displayLabel(ev.kind)}
                      </Badge>

                    </div>
                    {summarizePayload(ev.payload) && (
                      <div className="text-xs text-[var(--fg-muted)] mt-1 truncate">
                        {summarizePayload(ev.payload)}
                      </div>
                    )}
                  </div>

                  <div
                    dir="ltr"
                    className="text-[11px] text-[var(--fg-soft)] shrink-0 flex items-center gap-1 mt-1"
                  >
                    <Clock className="h-3 w-3" />
                    {formatTs(ev.ts)}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default ActivityPage;
