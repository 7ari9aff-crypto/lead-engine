import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

path = r"d:\lead generation\web\src\pages\Activity.tsx"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

# 1. Update iconForKind
c = c.replace(
    '''function iconForKind(kind: string) {
  if (kind.startsWith("agent.")) return <Bot className="h-4 w-4" />;''',
    '''function iconForKind(kind: string) {
  if (kind.startsWith("operator.")) return <ShieldCheck className="h-4 w-4 text-emerald-400" />;
  if (kind.startsWith("agent.")) return <Bot className="h-4 w-4" />;'''
)

# 2. Update toneForKind
c = c.replace(
    '''function toneForKind(kind: string): "info" | "accent" | "warn" | "default" {
  if (kind.startsWith("agent.")) return "accent";''',
    '''function toneForKind(kind: string): "info" | "accent" | "warn" | "default" {
  if (kind.startsWith("operator.")) return "accent";
  if (kind.startsWith("agent.")) return "accent";'''
)

# 3. Update KIND_LABELS
c = c.replace(
    '''  "lead.rejected": "رُفض عميل محتمل",
};''',
    '''  "lead.rejected": "رُفض عميل محتمل",
  "operator.export.csv": "تنزيل ملف CSV",
  "operator.export.instantly": "تصدير Instantly / Smartlead",
  "operator.export.webhook": "ترحيل إلى Webhook / CRM",
  "operator.icp.saved": "حفظ معايير الاستهداف",
  "operator.icp.activated": "تفعيل نسخة معايير جديدة",
  "operator.leads.verified": "فحص إيميلات جماعي",
};'''
)

# 4. Update events memoization
c = c.replace(
    '''  const events = useMemo<ActivityEvent[]>(() => {
    const raw = data?.events ?? [];
    if (filter === "all") return raw;
    return raw.filter((e) => e.kind?.startsWith(filter));
  }, [data, filter]);''',
    '''  const auditActions = useMemo(() => loadAuditLog(), [data]);

  const events = useMemo<ActivityEvent[]>(() => {
    const raw = data?.events ?? [];
    const auditMapped: ActivityEvent[] = auditActions.map((a) => ({
      id: a.id,
      kind: `operator.${a.kind}`,
      organization_id: "local",
      payload: { title: a.title, desc: a.description, count: a.targetCount },
      created_at: a.timestamp,
    }));

    const all = [...auditMapped, ...raw].sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    );

    if (filter === "all") return all;
    if (filter === "operator") return all.filter((e) => e.kind?.startsWith("operator."));
    return all.filter((e) => e.kind?.startsWith(filter));
  }, [data, auditActions, filter]);'''
)

# 5. Update title description
c = c.replace(
    '''title="سجل النشاط"
        description="آخر أحداث المنصة بالترتيب الزمني — مهام، تشغيل وكلاء، وموافقات"''',
    '''title="سجل النشاط والتدقيق (Audit Trail)"
        description="خط زمني موثق لكافة إجراءات المشغل، عمليات التصدير، قرارات الوكلاء، والمهام المنفذة"'''
)

with open(path, "w", encoding="utf-8") as f:
    f.write(c)
print("Activity.tsx successfully updated with full audit trail!")
