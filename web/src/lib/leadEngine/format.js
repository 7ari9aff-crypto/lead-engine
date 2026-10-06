// Shared formatting helpers (language-aware, Gregorian + Latin digits everywhere).
const NUM = (lang) => (lang === "ar" ? "ar-u-nu-latn" : "en-US");

export function fmtDuration(ms, lang) {
  if (ms == null || !isFinite(ms) || ms < 0) return "—";
  const mins = Math.max(1, Math.round(ms / 60000));
  const d = Math.floor(mins / 1440);
  const h = Math.floor((mins % 1440) / 60);
  const m = mins % 60;
  const ar = lang === "ar";
  const parts = [];
  if (d) parts.push(ar ? `${d} ${d === 1 ? "يوم" : "أيام"}` : `${d}d`);
  if (h) parts.push(ar ? `${h} ${h <= 10 && h > 2 ? "ساعات" : "ساعة"}` : `${h}h`);
  if (m && !d) parts.push(ar ? `${m} دقيقة` : `${m}m`);
  return parts.join(ar ? " و" : " ") || (ar ? "أقل من دقيقة" : "<1m");
}

export function fmtDate(iso, lang) {
  return new Intl.DateTimeFormat(NUM(lang), { dateStyle: "medium" }).format(new Date(iso));
}

export function fmtNum(n, lang) {
  return Number(n || 0).toLocaleString(NUM(lang));
}

// "has an identified decision maker" — one place, used by queue + detail
export function hasContact(lead) {
  const n = lead?.contact?.name;
  return !!n && n !== "—" && n !== "غير محدد بعد";
}

// Mock company data is stored in Arabic; the labels the UI itself shows around it get translated.
const DATA_EN = [
  ["فريق المبيعات", "Sales team"], ["حجم الشركة", "Company size"], ["القطاع", "Industry"], ["الموقع الجغرافي", "Location"],
  ["الموقع الإلكتروني", "Website"], ["الموقع", "Location"], ["النموذج", "Business model"], ["نموذج الإيراد", "Revenue model"],
  ["اسم الشركة", "Company name"], ["عدد الموظفين", "Employees"], ["صانع القرار", "Decision maker"],
  ["غير مؤكد", "Unconfirmed"], ["غير موثّق", "undocumented"], ["غير موجود", "none"], ["نعم", "Yes"], ["لا", "No"],
  ["موظف", "employees"], ["طازج", "fresh"], ["حديث", "recent"], ["قديم (أكثر من سنة)", "stale (over a year)"], ["قديم", "stale"],
  ["الرياض", "Riyadh"], ["جدة", "Jeddah"], ["الدمام", "Dammam"], ["دبي", "Dubai"], ["السعودية", "Saudi Arabia"], ["الإمارات", "UAE"],
  ["برمجيات مؤسسية", "Enterprise software"], ["لوجستيات", "Logistics"], ["الموقع الرسمي", "Official website"],
  ["السجل التجاري", "Commercial registry"], ["فحص مباشر", "Live check"], ["محتمل", "Likely"], ["أعضاء بلقب Sales", "members titled Sales"],
];
export function tr(text, lang) {
  if (lang === "ar" || typeof text !== "string") return text;
  let out = text;
  for (const [ar, en] of DATA_EN) out = out.split(ar).join(en);
  return out;
}
