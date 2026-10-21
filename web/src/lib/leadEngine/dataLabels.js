// Labels for VALUES that come from the database (city, industry, country).
//
// The DB stores these in English ("Riyadh", "dental", "SA") but the dashboard is
// Arabic-first, so they used to show as raw English inside an Arabic sentence.
// `tr()` in format.js goes the other way (Arabic mock data -> English) and does not
// touch them.
//
// Rules, kept deliberately conservative:
//  - exact match after trim + lowercase, never a substring (a company called
//    "Dental Riyadh Group" must not be rewritten);
//  - an unknown value is returned untouched (better English than a wrong guess);
//  - English mode returns the value untouched.

const CITY_AR = {
  riyadh: "الرياض",
  jeddah: "جدة",
  dammam: "الدمام",
  khobar: "الخبر",
  mecca: "مكة المكرمة",
  makkah: "مكة المكرمة",
  medina: "المدينة المنورة",
  madinah: "المدينة المنورة",
  taif: "الطائف",
  tabuk: "تبوك",
  abha: "أبها",
  dubai: "دبي",
  "abu dhabi": "أبوظبي",
  sharjah: "الشارقة",
  doha: "الدوحة",
  kuwait: "الكويت",
  "kuwait city": "مدينة الكويت",
  manama: "المنامة",
  muscat: "مسقط",
  cairo: "القاهرة",
  alexandria: "الإسكندرية",
  giza: "الجيزة",
  amman: "عمّان",
};

const INDUSTRY_AR = {
  dental: "طب الأسنان",
  "dental clinic": "عيادة أسنان",
  "dental clinics": "عيادات الأسنان",
  dentistry: "طب الأسنان",
  healthcare: "الرعاية الصحية",
  logistics: "اللوجستيات",
  saas: "SaaS",
  fintech: "التقنية المالية",
  "real estate": "العقارات",
  retail: "التجزئة",
  education: "التعليم",
  restaurants: "المطاعم",
  construction: "المقاولات",
  manufacturing: "التصنيع",
};

const COUNTRY_AR = {
  sa: "السعودية",
  "saudi arabia": "السعودية",
  ae: "الإمارات",
  uae: "الإمارات",
  "united arab emirates": "الإمارات",
  qa: "قطر",
  kw: "الكويت",
  bh: "البحرين",
  om: "عُمان",
  eg: "مصر",
  egypt: "مصر",
  jo: "الأردن",
};

function lookup(table, value, lang) {
  if (lang !== "ar" || typeof value !== "string") return value;
  const hit = table[value.trim().toLowerCase()];
  return hit || value;
}

export const trCity = (value, lang) => lookup(CITY_AR, value, lang);
export const trIndustry = (value, lang) => lookup(INDUSTRY_AR, value, lang);
export const trCountry = (value, lang) => lookup(COUNTRY_AR, value, lang);

// "Riyadh, Saudi Arabia" / "Riyadh، السعودية": translate each comma-separated part
// by its own table so a free-text location still reads naturally.
export function trLocation(value, lang) {
  if (lang !== "ar" || typeof value !== "string") return value;
  const parts = value.split(/\s*[,،]\s*/);
  const out = parts.map((p) => {
    const k = p.trim().toLowerCase();
    return CITY_AR[k] || COUNTRY_AR[k] || p;
  });
  return out.join("، ");
}

// Search must find what the user SEES. The screen shows "الرياض" but the DB holds "Riyadh",
// so a plain substring match on the stored value finds nothing when an Arabic user types
// the Arabic name. Match the stored value and its Arabic label.
export function matchesLocation(stored, query) {
  const q = String(query || "").trim().toLowerCase();
  if (!q) return true;
  const raw = String(stored || "").toLowerCase();
  if (raw.includes(q)) return true;
  return trLocation(String(stored || ""), "ar").toLowerCase().includes(q);
}
