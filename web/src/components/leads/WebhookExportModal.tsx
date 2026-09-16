import { useState } from "react";
import { Send, CheckCircle2, AlertCircle, Globe, ExternalLink, X, Shield, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { toast } from "sonner";
import { logAuditAction } from "@/lib/audit";
import type { LeadRow } from "@/lib/api";

interface WebhookExportModalProps {
  open: boolean;
  onClose: () => void;
  leads: LeadRow[];
  selectedCount?: number;
}

const PRESETS = [
  { name: "Zapier", icon: "⚡", placeholder: "https://hooks.zapier.com/hooks/catch/..." },
  { name: "Make / Integromat", icon: "🟣", placeholder: "https://hook.eu1.make.com/..." },
  { name: "n8n", icon: "🔀", placeholder: "https://your-n8n.app/webhook/..." },
  { name: "Custom CRM", icon: "🌐", placeholder: "https://your-api.com/api/v1/leads" },
];

export function WebhookExportModal({ open, onClose, leads, selectedCount = 0 }: WebhookExportModalProps) {
  const [url, setUrl] = useState(() => localStorage.getItem("leadEngine.lastWebhookUrl") || "");
  const [sending, setSending] = useState(false);
  const [testing, setTesting] = useState(false);
  const [includeFullDetails, setIncludeFullDetails] = useState(true);

  if (!open) return null;

  const targetCount = selectedCount > 0 ? selectedCount : leads.length;

  const handleTestPing = async () => {
    if (!url.trim().startsWith("http")) {
      toast.error("يرجى إدخال رابط Webhook صالح يبدأ بـ http أو https");
      return;
    }
    setTesting(true);
    try {
      const pingPayload = {
        event: "ping",
        source: "Lead Engine",
        timestamp: new Date().toISOString(),
        test: true,
        message: "Ping test from Lead Engine Webhook integration",
      };
      const res = await fetch(url.trim(), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(pingPayload),
      });
      if (res.ok) {
        toast.success(`تم الاتصال بنجاح! كود الاستجابة: HTTP ${res.status}`);
      } else {
        toast.warning(`تم الإرسال ولكن الخادم أعاد كود: HTTP ${res.status}`);
      }
    } catch (e: any) {
      toast.error(`تعذر الوصول للرابط (تحقق من CORS أو الرابط): ${e.message || "خطأ اتصال"}`);
    } finally {
      setTesting(false);
    }
  };

  const handleSend = async () => {
    if (!url.trim().startsWith("http")) {
      toast.error("يرجى إدخال رابط Webhook صالح يبدأ بـ http أو https");
      return;
    }

    setSending(true);
    try {
      localStorage.setItem("leadEngine.lastWebhookUrl", url.trim());

      const payloadLeads = leads.map((l) => {
        if (!includeFullDetails) {
          return {
            name: l.name,
            email: l.email,
            phone: l.phone,
            city: l.city,
            website: l.website || l.domain,
            decision_maker: l.decision_maker,
            score: l.score,
          };
        }
        return l;
      });

      const payload = {
        event: "leads.exported",
        batch_id: `batch_${Date.now()}`,
        count: payloadLeads.length,
        timestamp: new Date().toISOString(),
        leads: payloadLeads,
      };

      const res = await fetch(url.trim(), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (res.ok || res.status === 200 || res.status === 201 || res.status === 202) {
        toast.success(`تم إرسال ${payloadLeads.length} عميل بنجاح إلى الـ Webhook!`);
        logAuditAction(
          "export.webhook",
          `إرسال ${payloadLeads.length} عميل إلى Webhook`,
          `تم الإرسال إلى الرابط: ${url.trim()}`,
          payloadLeads.length,
          { url: url.trim(), status: res.status }
        );
        onClose();
      } else {
        toast.warning(`أرسل الخادم استجابة: HTTP ${res.status}`);
      }
    } catch (e: any) {
      toast.error(`خطأ أثناء إرسال البيانات: ${e.message || "تعذر الإرسال"}`);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4 animate-in fade-in duration-150">
      <div className="w-full max-w-lg rounded-2xl border border-[var(--border)] bg-[var(--bg-elev)] shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="px-5 py-4 border-b border-[var(--border-soft)] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="p-2 rounded-xl bg-[var(--accent)]/15 text-[var(--accent)]">
              <Send className="h-4 w-4" />
            </span>
            <div>
              <h3 className="text-sm font-bold text-[var(--fg)]">ترحيل مباشر إلى Webhook / CRM</h3>
              <p className="text-[11px] text-[var(--fg-muted)]">Zapier, Make, n8n, Slack, HubSpot أو أي API مخصص</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1 rounded-lg text-[var(--fg-muted)] hover:text-[var(--fg)] hover:bg-[var(--bg-soft)]">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="p-5 space-y-4 text-xs">
          {/* Presets */}
          <div>
            <label className="text-[11px] font-semibold text-[var(--fg-soft)] block mb-1.5">المنصات المدعومة وتنسيقات الروابط:</label>
            <div className="grid grid-cols-2 gap-2">
              {PRESETS.map((p) => (
                <button
                  key={p.name}
                  type="button"
                  onClick={() => {
                    if (!url) setUrl(p.placeholder);
                  }}
                  className="p-2 rounded-xl border border-[var(--border-soft)] bg-[var(--bg-soft)] hover:border-[var(--accent)] text-right flex items-center gap-2 transition-all"
                >
                  <span className="text-base">{p.icon}</span>
                  <span className="font-semibold text-[var(--fg)]">{p.name}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Webhook URL Input */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-[11px] font-semibold text-[var(--fg)]">رابط الـ Webhook (Endpoint URL):</label>
              <button
                type="button"
                onClick={handleTestPing}
                disabled={testing || !url.trim()}
                className="text-[10px] text-[var(--accent)] hover:underline flex items-center gap-1"
              >
                {testing ? <RefreshCw className="h-3 w-3 animate-spin" /> : <Globe className="h-3 w-3" />}
                اختبار الاتصال (Ping)
              </button>
            </div>
            <Input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://hooks.zapier.com/hooks/catch/..."
              className="text-xs font-mono"
            />
          </div>

          {/* Options */}
          <div className="rounded-xl border border-[var(--border-soft)] bg-[var(--bg-soft)] p-3 space-y-2">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={includeFullDetails}
                onChange={(e) => setIncludeFullDetails(e.target.checked)}
                className="rounded text-[var(--accent)]"
              />
              <span className="text-[11px] text-[var(--fg)] font-medium">تضمين كافة بيانات التقييم والمصادر وسجل التحقق الكامل</span>
            </label>
            <div className="flex items-center justify-between text-[11px] text-[var(--fg-muted)] pt-1 border-t border-[var(--border-soft)]">
              <span>عدد العملاء المراد ترحيلهم:</span>
              <strong className="text-[var(--accent)] font-bold">{targetCount} عميل</strong>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-5 py-3.5 border-t border-[var(--border-soft)] bg-[var(--bg-soft)]/50 flex items-center justify-between gap-3">
          <Button variant="ghost" size="sm" onClick={onClose} disabled={sending}>
            إلغاء
          </Button>
          <Button variant="primary" size="sm" onClick={handleSend} loading={sending}>
            <Send className="h-3.5 w-3.5 me-1" />
            إرسال الآن ({targetCount})
          </Button>
        </div>
      </div>
    </div>
  );
}
