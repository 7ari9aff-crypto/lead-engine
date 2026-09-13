/**
 * ICP criteria — stage 2 gate as a first-class page: versioned criteria the
 * user controls ("ما ينفع وما لا ينفع لي"). The ACTIVE version drives search
 * planning, deterministic gates, and re-qualification.
 */
import { useState } from "react";
import { Loader2, CheckCircle2, History, Plus, Save, SlidersHorizontal } from "lucide-react";
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

const SIMPLE_TEMPLATE = {
  industry: "dental",
  cities: [{ name: "Jeddah", ar: "جدة" }],
  keywords_en: ["dental clinic"],
  keywords_ar: ["عيادة أسنان"],
  criteria: { min_branches: 1, notes: "عيادات حقيقية — لا دلائل ولا مجمّعات" },
};

export function IcpPage() {
  const { data, loading, refresh } = useLiveData(() => apiGetExtra.icps("agentic"), 15000);
  const [json, setJson] = useState("");
  const [saving, setSaving] = useState(false);
  const versions = data?.versions || [];
  const active = data?.active;

  async function save() {
    let definition: any;
    try {
      definition = JSON.parse(json);
    } catch {
      return toast.error("الـJSON غير صالح");
    }
    setSaving(true);
    try {
      await apiPostExtra.icpCreate(definition, "agentic", true, "manual");
      toast.success("انحفظت نسخة معايير جديدة و became نشطة");
      setJson("");
      refresh();
    } catch (e) {
      toast.error(friendlyError(e));
    } finally {
      setSaving(false);
    }
  }

  async function activate(id: string) {
    try {
      await apiPostExtra.icpActivate(id);
      toast.success("اننشطت النسخة — كل البحث والتأهيل الجاي عليها");
      refresh();
    } catch (e) {
      toast.error(friendlyError(e));
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        icon={<SlidersHorizontal className="h-5 w-5" />}
        title="معايير الفلترة (ICP)"
        description="ما ينفع وما لا ينفع لي — نسخ versioned؛ النسخة النشطة هي الفلتر لكل البحث والتأهيل"
      />

      <div className="grid lg:grid-cols-2 gap-4 items-start">
        <Card>
          <CardContent className="p-4 space-y-3">
            <div className="flex items-center gap-2">
              <span className="text-[13px] font-bold">النسخة النشطة</span>
              {active ? (
                <Badge variant="success" className="text-[10px]">
                  <CheckCircle2 className="h-3 w-3 inline me-1" />
                  {active.slug} {active.version}
                </Badge>
              ) : (
                <Badge variant="warn" className="text-[10px]">لا يوجد — الفلترة الحتمية معطلة</Badge>
              )}
            </div>
            {active && (
              <pre className="text-[11.5px] leading-5 bg-[var(--bg-soft)] rounded-lg p-3 overflow-x-auto"
                   dir="ltr">
                {JSON.stringify(active.definition, null, 2)}
              </pre>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4 space-y-3">
            <div className="text-[13px] font-bold flex items-center gap-1.5">
              <Plus className="h-4 w-4" /> نسخة معايير جديدة
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" className="text-[12px] h-8"
                      onClick={() => setJson(JSON.stringify(SIMPLE_TEMPLATE, null, 2))}>
                قالب جاهز (عيادات أسنان)
              </Button>
            </div>
            <textarea
              value={json}
              onChange={(e) => setJson(e.target.value)}
              rows={12}
              dir="ltr"
              placeholder='{"industry": "...", "cities": [{"name": "..."}], "criteria": {"min_branches": 1}}'
              className="w-full rounded-xl border border-[var(--border-soft)] bg-[var(--bg-soft)] px-3 py-2.5 text-[12px] leading-5 outline-none focus:border-[var(--accent)] font-mono"
            />
            <Button variant="primary" onClick={save} disabled={saving || !json.trim()} className="w-full">
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              احفظ وانسّط
            </Button>
            <p className="text-[10.5px] text-[var(--fg-soft)] leading-4">
              كل حفظ يعمل نسخة جديدة — القديمة تبقى retired في السجل (تراجع كامل)،
              والتنشيط يعيد تأهيل الـleads المخزنة من صفحة المراجعة بدون بحث جديد.
            </p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardContent className="p-4 space-y-2">
          <div className="text-[13px] font-bold flex items-center gap-1.5">
            <History className="h-4 w-4" /> سجل الإصدارات
          </div>
          {loading && !data ? <Spinner /> : versions.length === 0 ? (
            <div className="text-[12.5px] text-[var(--fg-muted)] py-3">لا إصدارات — ابدأ بالقالب الجاهز فوق.</div>
          ) : versions.map((v) => (
            <div key={v.icp_version_id}
                 className="flex items-center gap-2 rounded-lg border border-[var(--border-soft)] px-3 py-2">
              <span className="text-[12.5px] font-semibold">{v.slug} {v.version}</span>
              <Badge variant={v.status === "active" ? "success" : v.status === "retired" ? "default" : "info"}
                     className="text-[10px]">{v.status}</Badge>
              <span className="text-[10px] text-[var(--fg-soft)]">{v.source}</span>
              <span className="ms-auto text-[10px] text-[var(--fg-soft)] tnum">{v.created_at?.slice(0, 16)}</span>
              {v.status !== "active" && (
                <Button variant="outline" className="text-[11px] h-7"
                        onClick={() => activate(v.icp_version_id)}>
                  <CheckCircle2 className="h-3 w-3" /> نشّط
                </Button>
              )}
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
