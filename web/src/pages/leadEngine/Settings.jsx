import React from "react";
import { useLeadEngine } from "@/lib/leadEngine/store";
import { PageHeader } from "@/components/leadEngine/PageHeader";
import { Pill } from "@/components/leadEngine/primitives";
import { Building2, Globe, ShieldCheck, Users } from "lucide-react";

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
      </div>
    </>
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
