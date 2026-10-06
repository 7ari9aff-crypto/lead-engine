import React, { useState } from "react";
import { cn } from "@/lib/utils";
import { useLeadEngine } from "@/lib/leadEngine/store";
import { PageHeader } from "@/components/leadEngine/PageHeader";
import { Pill, TimeAgo } from "@/components/leadEngine/primitives";
import { KeyRound, Plus, RotateCw, Zap, Lock, Check } from "lucide-react";

// one inline form handles both "add" and "rotate" — the key is masked immediately and never kept
function KeyForm({ ar, services, fixedService, onSubmit, onCancel }) {
  const [service, setService] = useState(fixedService || services[0] || "");
  const [key, setKey] = useState("");
  return (
    <div className="card-surface p-4 flex flex-col sm:flex-row gap-2 sm:items-end animate-scale-in">
      {!fixedService && (
        <label className="text-[11px] text-muted-foreground flex-1">{ar ? "الخدمة" : "Service"}
          <select value={service} onChange={(e) => setService(e.target.value)} className="mt-1 w-full h-9 px-2 rounded-lg border border-input bg-background text-sm text-foreground focus-ring">
            {services.map((s) => <option key={s}>{s}</option>)}
          </select>
        </label>
      )}
      <label className="text-[11px] text-muted-foreground flex-[2]">{ar ? "المفتاح" : "API key"}
        <input autoFocus type="password" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} onKeyDown={(e) => e.key === "Enter" && key.trim() && onSubmit(service, key)}
          className="mt-1 w-full h-9 px-3 rounded-lg border border-input bg-background text-sm text-foreground focus-ring font-mono" dir="ltr" />
      </label>
      <div className="flex gap-2">
        <button disabled={!key.trim()} onClick={() => onSubmit(service, key)} className="h-9 px-4 rounded-lg bg-primary text-primary-foreground text-sm font-medium disabled:opacity-40">{ar ? "حفظ" : "Save"}</button>
        <button onClick={onCancel} className="h-9 px-3 rounded-lg border border-border text-sm">{ar ? "إلغاء" : "Cancel"}</button>
      </div>
    </div>
  );
}

export default function Credentials() {
  const { t, lang, credentials, addCredential, testCredential, rotateCredential } = useLeadEngine();
  const ar = lang === "ar";
  const [testing, setTesting] = useState(null);
  const [okFlash, setOkFlash] = useState(null);
  const [form, setForm] = useState(null); // null | "add" | credential id (rotate)

  const test = (id) => {
    setTesting(id);
    setTimeout(() => { setTesting(null); testCredential(id); setOkFlash(id); setTimeout(() => setOkFlash(null), 2500); }, 1000);
  };
  const missing = credentials.filter((c) => !c.connected).map((c) => c.service);
  const knownServices = ["Gemini", "Exa", "LinkedIn", "ZoomInfo", "Google Maps"];
  const addable = [...new Set([...missing, ...knownServices.filter((s) => !credentials.some((c) => c.service === s))])];

  return (
    <>
      <PageHeader title={t("creds.title")} subtitle={t("creds.noSecret")}
        actions={addable.length > 0 && <button onClick={() => setForm("add")} className="focus-ring rounded-lg bg-primary text-primary-foreground px-3.5 py-2 text-sm font-medium hover:opacity-90 inline-flex items-center gap-1.5"><Plus className="w-4 h-4" /> {ar ? "إضافة بيانات اعتماد" : "Add credential"}</button>} />
      <div className="px-4 lg:px-8 py-6 max-w-[1100px] space-y-3">
        <div className="rounded-lg bg-secondary border border-border p-3 flex gap-2 text-xs text-muted-foreground">
          <Lock className="w-4 h-4 shrink-0" />
          <span>{ar ? "بعد الحفظ تُخفى المفاتيح ولا تظهر مرة أخرى. لا نعرض إلا آخر 4 أحرف للتعرّف عليها." : "Saved keys are hidden and never shown again. Only the last 4 characters are visible so you can recognise them."}</span>
        </div>

        {form === "add" && <KeyForm ar={ar} services={addable} onCancel={() => setForm(null)} onSubmit={(s, k) => { if (addCredential(s, k)) setForm(null); }} />}

        {credentials.map((c) => (
          <div key={c.id} className="space-y-2">
            <div className="card-surface p-4 flex flex-col sm:flex-row sm:items-center gap-3">
              <div className="flex items-center gap-3 flex-1 min-w-0">
                <div className={cn("w-10 h-10 rounded-lg grid place-items-center", c.connected ? "bg-[hsl(var(--success-soft))] text-[hsl(var(--success-ink))]" : "bg-muted text-muted-foreground")}><KeyRound className="w-5 h-5" /></div>
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold">{c.service}</h3>
                    <Pill tone={c.connected ? "success" : "danger"}>{c.connected ? (ar ? "مربوط" : "Connected") : (ar ? "ناقص" : "Missing")}</Pill>
                  </div>
                  <div className="text-xs text-muted-foreground mt-0.5"><span className="font-mono" dir="ltr">{c.masked}</span> · {c.note}</div>
                </div>
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                {c.lastTested && <span className="text-[11px] text-muted-foreground hidden sm:inline">{ar ? "آخر اختبار" : "Tested"} <TimeAgo iso={c.lastTested} /></span>}
                {c.connected ? (
                  <>
                    <button onClick={() => test(c.id)} disabled={testing === c.id} className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium hover:bg-muted transition inline-flex items-center gap-1.5 disabled:opacity-60">
                      {testing === c.id ? <RotateCw className="w-3.5 h-3.5 animate-spin" /> : okFlash === c.id ? <Check className="w-3.5 h-3.5 text-[hsl(var(--success))]" /> : <Zap className="w-3.5 h-3.5" />}
                      {okFlash === c.id ? <span className="text-[hsl(var(--success-ink))]">{ar ? "الاتصال سليم" : "Works"}</span> : (ar ? "اختبار" : "Test")}
                    </button>
                    <button onClick={() => setForm(c.id)} className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium hover:bg-muted transition inline-flex items-center gap-1.5"><RotateCw className="w-3.5 h-3.5" /> {ar ? "تغيير المفتاح" : "Replace key"}</button>
                  </>
                ) : (
                  <button onClick={() => setForm(c.id)} className="rounded-lg bg-primary text-primary-foreground px-3 py-1.5 text-xs font-medium hover:opacity-90 inline-flex items-center gap-1.5"><Plus className="w-3.5 h-3.5" /> {ar ? "إدخال المفتاح" : "Enter key"}</button>
                )}
              </div>
            </div>
            {form === c.id && <KeyForm ar={ar} fixedService={c.service} services={[c.service]} onCancel={() => setForm(null)}
              onSubmit={(s, k) => { const ok = c.connected ? rotateCredential(c.id, k) : addCredential(s, k); if (ok) setForm(null); }} />}
          </div>
        ))}
      </div>
    </>
  );
}
