import React, { useEffect, useState } from "react";
import { useLeadEngine } from "@/lib/leadEngine/store";
import { PageHeader } from "@/components/leadEngine/PageHeader";
import { Pill } from "@/components/leadEngine/primitives";
import { Building2, Globe, ShieldCheck, Users, Loader2 } from "lucide-react";
import {
  mfaListFactors, mfaEnrollTotp, mfaChallengeAndVerify, mfaUnenroll,
  supabaseConfigured,
} from "@/lib/supabase";

export default function Settings() {
  const { t, lang, toggleLang, currentUser, providers, credentials } = useLeadEngine();
  const ar = lang === "ar";
  // only things we can actually derive from data — no invented "database / queue / workers" lights
  const provOk = providers.every((p) => p.status === "OPERATIONAL");
  const credOk = credentials.every((c) => c.connected);
  const items = [
    { label: ar ? "المزودون" : "Providers", ok: provOk, text: provOk ? (ar ? "سليمة" : "Healthy") : (ar ? "تحتاج انتباهًا" : "Needs attention") },
    { label: ar ? "بيانات الاعتماد" : "Credentials", ok: credOk, text: credOk ? (ar ? "مكتملة" : "Complete") : (ar ? "ناقصة" : "Incomplete") },
    { label: ar ? "الإرسال التلقائي" : "Automatic sending", ok: true, text: ar ? "معطّل دائمًا" : "Always off" },
    { label: ar ? "كشف بيانات الاتصال" : "Contact reveal", ok: true, text: ar ? "بسبب مسجّل" : "Reason required" },
  ];

  return (
    <>
      <PageHeader title={t("settings.title")} subtitle={ar ? "المؤسسة، اللغة، الصلاحيات، وحالة الأمان." : "Organization, language, roles, and safeguards."} />
      <div className="px-4 lg:px-8 py-6 max-w-[1100px] space-y-5">
        <section className="card-surface p-5">
          <h3 className="text-sm font-semibold mb-4 flex items-center gap-2"><Building2 className="w-4 h-4 text-muted-foreground" /> {t("nav.organization")}</h3>
          <div className="grid sm:grid-cols-2 gap-4 text-sm">
            <Field label={ar ? "المؤسسة" : "Organization"} value={currentUser.organization} />
            <Field label={ar ? "المستخدم" : "User"} value={currentUser.name} />
            <Field label={ar ? "البريد" : "Email"} value={<span dir="ltr">{currentUser.email}</span>} />
            <Field label={ar ? "الدور" : "Role"} value={<Pill tone="primary">{currentUser.role === "admin" ? (ar ? "مدير" : "Admin") : (ar ? "عضو" : "Member")}</Pill>} />
          </div>
          <p className="text-xs text-muted-foreground mt-4 pt-4 border-t border-border">{ar ? "كل مؤسسة ترى بياناتها فقط." : "Each organization sees only its own data."}</p>
        </section>

        <section className="card-surface p-5">
          <h3 className="text-sm font-semibold mb-4 flex items-center gap-2"><Globe className="w-4 h-4 text-muted-foreground" /> {ar ? "اللغة" : "Language"}</h3>
          <div className="flex items-center justify-between gap-3">
            <span className="text-sm">{ar ? "العربية" : "English"}</span>
            <button onClick={toggleLang} className="rounded-lg border border-border px-4 py-2 text-sm font-medium hover:bg-muted transition">{ar ? "Switch to English" : "التبديل إلى العربية"}</button>
          </div>
          <p className="text-xs text-muted-foreground mt-3">{ar ? "تتغير النصوص فقط وتصميم الصفحة يبقى ثابتًا. بيانات الشركات تبقى بلغتها الأصلية." : "Only the text changes; the page layout stays the same. Company data stays in its original language."}</p>
        </section>

        <section className="card-surface p-5">
          <h3 className="text-sm font-semibold mb-4 flex items-center gap-2"><ShieldCheck className="w-4 h-4 text-muted-foreground" /> {ar ? "الأمان والحالة" : "Safeguards & status"}</h3>
          <div className="grid sm:grid-cols-2 gap-2.5">
            {items.map((h) => (
              <div key={h.label} className="flex items-center justify-between rounded-lg border border-border px-3 py-2.5">
                <span className="text-sm">{h.label}</span>
                <Pill tone={h.ok ? "success" : "warning"}>{h.text}</Pill>
              </div>
            ))}
          </div>
        </section>

        <section className="card-surface p-5">
          <h3 className="text-sm font-semibold mb-4 flex items-center gap-2"><Users className="w-4 h-4 text-muted-foreground" /> {ar ? "الأدوار والصلاحيات" : "Roles & permissions"}</h3>
          <div className="space-y-2 text-sm">
            <RoleRow role={ar ? "مدير" : "Admin"} perms={ar ? "إدارة الفريق، بيانات الاعتماد، التكاملات، المزودون، سجل التدقيق، الإعدادات" : "Team, credentials, integrations, providers, audit log, settings"} />
            <RoleRow role={ar ? "عضو" : "Member"} perms={ar ? "تشغيل البحث، تصفح العملاء والوظائف، ومراجعة العملاء" : "Run research, browse leads and jobs, review leads"} />
          </div>
        </section>

        {supabaseConfigured && <MfaSection ar={ar} />}
      </div>
    </>
  );
}

function MfaSection({ ar }) {
  const [factors, setFactors] = useState(null);
  const [phase, setPhase] = useState("idle"); // idle | enrolling | verifying
  const [qrSvg, setQrSvg] = useState("");
  const [secret, setSecret] = useState("");
  const [factorId, setFactorId] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const f = await mfaListFactors();
      setFactors(f.totp || []);
    } catch { setFactors([]); }
  };
  useEffect(() => { load(); }, []);

  const startEnroll = async () => {
    setError(""); setBusy(true);
    try {
      const d = await mfaEnrollTotp("lead-engine");
      setQrSvg(d.totp?.qr_code || "");
      setSecret(d.totp?.secret || "");
      setFactorId(d.id);
      setPhase("verifying");
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };

  const verify = async () => {
    setError(""); setBusy(true);
    try {
      await mfaChallengeAndVerify(factorId, code.trim());
      setPhase("idle"); setCode(""); setQrSvg(""); setSecret("");
      await load();
    } catch (e) { setError(e.message || "invalid code"); } finally { setBusy(false); }
  };

  const unenroll = async (id) => {
    setError(""); setBusy(true);
    try { await mfaUnenroll(id); await load(); } catch (e) { setError(e.message); } finally { setBusy(false); }
  };

  return (
    <section className="card-surface p-5">
      <h3 className="text-sm font-semibold mb-4 flex items-center gap-2"><ShieldCheck className="w-4 h-4 text-muted-foreground" /> {ar ? "المصادقة الثنائية (TOTP)" : "Two-factor authentication (TOTP)"}</h3>
      {error && <div className="mb-3 p-2 rounded-lg bg-destructive/10 text-destructive text-xs">{error}</div>}
      {factors === null ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="w-4 h-4 animate-spin" />…</div>
      ) : factors.length > 0 && phase !== "verifying" ? (
        <div className="space-y-2 text-sm">
          {factors.map((f) => (
            <div key={f.id} className="flex items-center justify-between rounded-lg border border-border px-3 py-2.5">
              <span>{f.friendly_name || f.id.slice(0, 8)}</span>
              <button onClick={() => unenroll(f.id)} disabled={busy}
                className="text-xs text-destructive hover:underline">{ar ? "إزالة" : "Remove"}</button>
            </div>
          ))}
          <button onClick={startEnroll} disabled={busy}
            className="rounded-lg border border-border px-4 py-2 text-sm font-medium hover:bg-muted transition">
            {ar ? "أضف عاملًا آخر" : "Add another factor"}
          </button>
        </div>
      ) : phase !== "verifying" ? (
        <div className="space-y-3 text-sm">
          <p className="text-muted-foreground text-xs">{ar ? "فعّل التحقق عبر تطبيق المصادقة لتأمين حسابك." : "Secure your account with an authenticator app."}</p>
          <button onClick={startEnroll} disabled={busy}
            className="rounded-lg bg-primary text-primary-foreground px-4 py-2 text-sm font-medium hover:opacity-90 transition">
            {busy ? "…" : ar ? "تفعيل التحقق الثنائي" : "Enable 2FA"}
          </button>
        </div>
      ) : (
        <div className="space-y-3 text-sm">
          <div className="rounded-lg border border-border p-3 bg-white inline-block" dangerouslySetInnerHTML={{ __html: qrSvg }} />
          {secret && <p className="text-xs text-muted-foreground" dir="ltr">secret: <code className="font-mono">{secret}</code></p>}
          <div className="flex gap-2">
            <input value={code} onChange={(e) => setCode(e.target.value)} maxLength={6}
              inputMode="numeric" placeholder="123456" dir="ltr"
              className="rounded-lg border border-border px-3 py-2 font-mono tracking-widest w-32 bg-transparent" />
            <button onClick={verify} disabled={busy || code.length < 6}
              className="rounded-lg bg-primary text-primary-foreground px-4 py-2 text-sm font-medium disabled:opacity-50">
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : ar ? "تحقق" : "Verify"}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

function Field({ label, value }) {
  return (<div><div className="text-[11px] text-muted-foreground mb-1">{label}</div><div className="font-medium">{value}</div></div>);
}
function RoleRow({ role, perms }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-3 rounded-lg border border-border px-3 py-2.5">
      <span className="font-semibold w-24 shrink-0">{role}</span>
      <span className="text-muted-foreground text-xs">{perms}</span>
    </div>
  );
}
