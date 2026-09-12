// Human-friendly Arabic messaging layer.
// The dashboard is used by non-technical operators — no HTTP codes, no
// English errors, no identifiers ever reach the screen. Technical detail
// stays in the console for diagnostics only.

export function friendlyError(e: unknown): string {
  const anyErr = e as any;
  const raw = String(anyErr?.message ?? anyErr ?? "").trim();
  const status: number | undefined = anyErr?.status;

  // Supabase auth messages (come straight through from GoTrue)
  const lower = raw.toLowerCase();
  if (lower.includes("invalid login credentials")) return "البريد أو كلمة المرور مش صحيحة";
  if (lower.includes("email not confirmed")) return "فعّل بريدك الأول من رسالة التأكيد اللي وصلتك";
  if (lower.includes("user not found")) return "مفيش حساب بالبريد ده — سجل حساب جديد";
  if (lower.includes("too many requests") || lower.includes("rate limit")) return "طلبات كتير في وقت قصير — استنى دقيقة وجرّب تاني";
  if (lower.includes("failed to fetch") || lower.includes("networkerror") || lower.includes("load failed")) {
    return "تعذر الاتصال بالخدمة — اتأكد من اتصالك بالإنترنت وجرّب تاني";
  }
  if (status === 401 || lower.includes("not authenticated") || lower.includes("unauthorized")) {
    return "الجلسة خلصت — سجّل دخولك من جديد";
  }
  if (status === 403 || lower.includes("forbidden")) return "حسابك ملوش صلاحية للعملية دي";
  if (status === 404 || lower.includes("not found")) return "العنصر اللي بتطلبه مش موجود أو اتحذف";
  if (status === 429) return "وصلت للحد الأقصى للطلبات — استنى شوية وجرّب تاني";
  if (status == null && /500|internal server error/i.test(raw)) return "حصلت مشكلة مؤقتة في الخدمة — جرّب تاني بعد لحظات";
  if (status === 500 || (status && status >= 500)) return "حصلت مشكلة مؤقتة في الخدمة — جرّب تاني بعد لحظات";
  if (status === 422 || status === 400) {
    // Validation errors: the backend already writes them in Arabic
    if (/[\u0600-\u06FF]/.test(raw)) return raw;
    return "البيانات المدخلة مش مكتملة أو مش صحيحة";
  }
  if (/[\u0600-\u06FF]/.test(raw)) return raw; // backend Arabic messages pass through
  return "حصل خطأ غير متوقع — جرّب تاني، ولو تكرر حدّث الصفحة";
}

// ===== Shared label maps =====

export const ICP_LABELS: Record<string, string> = {
  v0_saudi_dental: "عيادات الأسنان — السعودية",
};

export const TASK_LABELS: Record<string, string> = {
  generate: "توليد",
  enrich: "إثراء",
  search: "بحث",
  verify_email: "تحقق بريد",
  discovery: "اكتشاف",
  qualification: "تأهيل",
};

export const ACTION_LABELS: Record<string, string> = {
  run_live: "تشغيل حقيقي على المنصات",
  run_benchmark: "تشغيل مهمة توليد",
  send_email: "إرسال بريد",
  delete_leads: "حذف بيانات",
  export_data: "تصدير بيانات",
  provision_tenant: "تجهيز مساحة جديدة",
};

// Tool names -> Arabic. Unmapped tools get a cleaned fallback.
export const TOOL_LABELS: Record<string, string> = {
  web_search: "بحث في الويب",
  company_search: "بحث شركات",
  people_search: "بحث أشخاص",
  enrich_company: "إثراء بيانات شركة",
  enrich_person: "إثراء بيانات شخص",
  find_email: "إيجاد بريد",
  verify_email: "فحص بريد",
  score_lead: "تقييم عميل",
  export_csv: "تصدير ملف",
  draft_email: "صياغة بريد",
};

export function toolLabel(name: string): string {
  return TOOL_LABELS[name] ?? name.replace(/_/g, " ");
}

// Chat tool-call arguments -> short human phrases (no raw JSON).
const ARG_LABELS: Record<string, string> = {
  query: "البحث",
  q: "البحث",
  keywords: "الكلمات",
  city: "المدينة",
  cities: "المدن",
  country: "الدولة",
  domain: "الموقع",
  company: "الشركة",
  email: "البريد",
  name: "الاسم",
  role: "الدور",
  limit: "الحد الأقصى",
  count: "العدد",
  icp: "ملف الاستهداف",
  provider: "المزود",
  model: "الموديل",
  language: "اللغة",
  url: "الرابط",
  path: "المسار",
  leads: "العملاء",
  job_id: "المهمة",
  lead_id: "العميل",
  title: "العنوان",
  subject: "الموضوع",
  body: "النص",
};

function shortValue(v: unknown): string {
  const s = typeof v === "string" ? v : Array.isArray(v) ? v.join("، ") : String(v ?? "");
  return s.length > 70 ? s.slice(0, 69) + "…" : s;
}

export function describeToolArgs(args: Record<string, unknown> | null | undefined): string[] {
  if (!args || typeof args !== "object") return [];
  return Object.entries(args)
    .filter(([, v]) => v != null && v !== "" && !(Array.isArray(v) && v.length === 0))
    .slice(0, 5)
    .map(([k, v]) => `${ARG_LABELS[k] ?? k}: ${shortValue(v)}`);
}

// Approval payload -> friendly key/value rows (no raw JSON blob).
export function describePayload(payload: unknown): { label: string; value: string }[] {
  if (!payload || typeof payload !== "object") return [];
  return Object.entries(payload as Record<string, unknown>)
    .filter(([, v]) => v != null && v !== "")
    .slice(0, 6)
    .map(([k, v]) => ({
      label: ARG_LABELS[k] ?? ACTION_LABELS[k] ?? k.replace(/_/g, " "),
      value: shortValue(v),
    }));
}
