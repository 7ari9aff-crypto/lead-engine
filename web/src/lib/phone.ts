// International E.164 Phone & WhatsApp Validator
// Detects country code, normalizes format, identifies mobile vs landline, and provides WhatsApp deep-links.

export interface PhoneInfo {
  raw: string;
  e164: string | null;
  digits: string;
  country: string;
  countryCode: string;
  isMobile: boolean;
  whatsappUrl: string | null;
  status: "verified_mobile" | "international" | "incomplete" | "invalid";
  statusLabel: string;
}

const COUNTRY_CODES: Array<{ prefix: string; country: string; minLen: number; maxLen: number; mobilePrefixes?: string[] }> = [
  { prefix: "1", country: "US/CA", minLen: 10, maxLen: 10 },
  { prefix: "44", country: "UK", minLen: 10, maxLen: 10, mobilePrefixes: ["7"] },
  { prefix: "49", country: "DE", minLen: 10, maxLen: 11, mobilePrefixes: ["15", "16", "17"] },
  { prefix: "33", country: "FR", minLen: 9, maxLen: 9, mobilePrefixes: ["6", "7"] },
  { prefix: "971", country: "UAE", minLen: 9, maxLen: 9, mobilePrefixes: ["5"] },
  { prefix: "966", country: "SA", minLen: 9, maxLen: 9, mobilePrefixes: ["5"] },
  { prefix: "20", country: "EG", minLen: 10, maxLen: 10, mobilePrefixes: ["10", "11", "12", "15"] },
  { prefix: "965", country: "KW", minLen: 8, maxLen: 8, mobilePrefixes: ["5", "6", "9"] },
  { prefix: "974", country: "QA", minLen: 8, maxLen: 8, mobilePrefixes: ["3", "5", "6", "7"] },
  { prefix: "973", country: "BH", minLen: 8, maxLen: 8, mobilePrefixes: ["3", "6"] },
  { prefix: "968", country: "OM", minLen: 8, maxLen: 8, mobilePrefixes: ["7", "9"] },
  { prefix: "90", country: "TR", minLen: 10, maxLen: 10, mobilePrefixes: ["5"] },
  { prefix: "91", country: "IN", minLen: 10, maxLen: 10, mobilePrefixes: ["6", "7", "8", "9"] },
  { prefix: "65", country: "SG", minLen: 8, maxLen: 8, mobilePrefixes: ["8", "9"] },
  { prefix: "61", country: "AU", minLen: 9, maxLen: 9, mobilePrefixes: ["4"] },
];

export function parseAndValidatePhone(phone?: string | null, companyName?: string | null): PhoneInfo {
  const raw = String(phone ?? "").trim();
  if (!raw) {
    return {
      raw: "",
      e164: null,
      digits: "",
      country: "—",
      countryCode: "",
      isMobile: false,
      whatsappUrl: null,
      status: "invalid",
      statusLabel: "غير متوفر",
    };
  }

  let digits = raw.replace(/[^0-9]/g, "");
  if (digits.startsWith("00")) digits = digits.substring(2);

  if (digits.length < 7) {
    return {
      raw,
      e164: null,
      digits,
      country: "غير معروف",
      countryCode: "",
      isMobile: false,
      whatsappUrl: null,
      status: "incomplete",
      statusLabel: "رقم غير مكتمل",
    };
  }

  // Detect matching country code
  let matchedCountry = "دولي";
  let matchedCode = "";
  let isMobile = true; // default assume mobile for messaging

  for (const c of COUNTRY_CODES) {
    if (digits.startsWith(c.prefix)) {
      matchedCountry = c.country;
      matchedCode = c.prefix;
      const national = digits.substring(c.prefix.length);
      if (c.mobilePrefixes && c.mobilePrefixes.length > 0) {
        isMobile = c.mobilePrefixes.some((p) => national.startsWith(p));
      }
      break;
    }
  }

  // Local number fallbacks without international prefix (e.g. 05x or standard 10-digits)
  if (!matchedCode) {
    if (digits.startsWith("0") && digits.length === 10) {
      // Common standard national number
      matchedCode = "Local";
      matchedCountry = "محلي";
    }
  }

  const e164 = digits.length >= 8 ? `+${digits}` : null;
  const greeting = `السلام عليكم ورحمة الله، بخصوص خدمات ${companyName || "المنشأة"} الكريمة.. حاب أستفسر من حضرتكم`;
  const whatsappUrl = digits.length >= 8 ? `https://wa.me/${digits}?text=${encodeURIComponent(greeting)}` : null;

  let status: PhoneInfo["status"] = "international";
  let statusLabel = "هاتف دولي";

  if (isMobile && whatsappUrl) {
    status = "verified_mobile";
    statusLabel = "جوال مؤهل لواتساب";
  } else if (!isMobile) {
    status = "international";
    statusLabel = "هاتف ثابت / أرضي";
  }

  return {
    raw,
    e164,
    digits,
    country: matchedCountry,
    countryCode: matchedCode,
    isMobile,
    whatsappUrl,
    status,
    statusLabel,
  };
}
