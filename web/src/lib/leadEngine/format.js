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

// Provider problems for the dashboard, one entry per PROVIDER (hunter/gemini/apollo
// each serve several tasks and would otherwise be listed once per task). Missing keys
// are split from real faults (cooldown / exhausted / disabled) because the fix and the
// destination page differ.
export function summarizeProviderIssues(providers = []) {
  const unconfigured = [];
  const faultyByName = new Map();
  for (const p of providers) {
    if (p.status === "UNCONFIGURED") {
      if (!unconfigured.includes(p.name)) unconfigured.push(p.name);
    } else if (p.status !== "OPERATIONAL" && !faultyByName.has(p.name)) {
      faultyByName.set(p.name, p);
    }
  }
  return { unconfigured, faulty: [...faultyByName.values()] };
}

// The extractor stores the <title> of whatever page it landed on as the company name,
// so a list shows "Home", "Dental Clinic" or a whole sentence cut with "...". When the
// stored name is clearly a page title and a domain exists, show the domain instead; the
// domain is the one stable identifier. Conservative on purpose: anything that could be a
// real name (including a doctor's name or a short brand) is left alone, and nothing is
// ever invented when there is no domain. Display only: the stored data is not changed.
const GENERIC_TITLES = new Set([
  "home", "homepage", "home page", "index", "welcome", "main", "main page", "default",
  "الرئيسية", "الصفحة الرئيسية", "الرئيسيه", "مرحبا", "مرحبًا",
  "dental clinic", "dental clinics", "dental services", "dental center", "dentistry",
  "dentist", "dentists", "clinic", "hospital", "services", "about us", "contact us",
  "طب الأسنان", "طب الاسنان", "عيادة أسنان", "عيادة اسنان", "عيادات أسنان", "مستشفى",
  // section headings of a clinic site, not the clinic
  "أطباؤنا", "اطباؤنا", "الطاقم الطبي", "فريقنا", "من نحن", "اتصل بنا", "خدماتنا",
  "قسم طب الأسنان", "قسم طب الاسنان", "الإدارة العامة لطب الأسنان",
]);
// "<generic service> in/ب <city>" is a search phrase, never a business name
const CITIES = "(?:riyadh|jeddah|jiddah|dammam|khobar|mecca|makkah|medina|saudi arabia|ksa|الرياض|جدة|جده|الدمام|الخبر|مكة|المدينة|السعودية)";
const GENERIC_IN_CITY = new RegExp(
  "^(?:(?:the )?(?:best )?(?:dental|dentist|dentists|dentistry|clinic|clinics|hospital|medical)(?: clinics?| centers?| centres?| services?)?"
  + "|(?:أفضل|افضل)?\\s*(?:عيادة|عيادات|مركز|مستشفى|اطباء|أطباء|طبيب)(?:\\s+(?:طب\\s+)?(?:أسنان|اسنان|الأسنان|الاسنان|الاطفال|الأطفال))*)"
  + "\\s*(?:in|at|near|\\-|:|\\||في|ب|بال)\\s*" + CITIES + "(?:\\s*[:|\\-].*)?$", "i");
const SENTENCE_HINT = /\b(is a|are a|is the|best|top|how to|what is|guide|reviews?|prices?|list of|near me)\b|\b20[12]\d\b|[?؟]|\.\.\.|…|\bفي (الرياض|جدة|السعودية)\b|\bأفضل\b|\bافضل\b/i;

export function displayCompanyName({ name, domain } = {}) {
  const n = (name || "").trim();
  const d = (domain || "").trim();
  if (!d) return n;
  if (!n) return d;
  const lower = n.toLowerCase();
  const isGeneric = GENERIC_TITLES.has(lower);
  const looksLikeSentence = n.length > 60 || SENTENCE_HINT.test(n);
  const isSearchPhrase = GENERIC_IN_CITY.test(n) || /\br\/[a-z0-9_]+/i.test(n);
  return isGeneric || looksLikeSentence || isSearchPhrase ? d : n;
}
