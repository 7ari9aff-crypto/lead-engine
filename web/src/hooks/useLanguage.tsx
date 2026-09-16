import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

type Language = "ar" | "en";

interface LanguageContextType {
  lang: Language;
  setLang: (lang: Language) => void;
  toggleLang: () => void;
  dir: "rtl" | "ltr";
  t: (key: string) => string;
}

const DICTIONARY: Record<string, { ar: string; en: string }> = {
  // Navigation & Sections
  "nav.workspace": { ar: "مساحة العمل", en: "Workspace" },
  "nav.data": { ar: "البيانات", en: "Data & Quality" },
  "nav.systems": { ar: "الأنظمة", en: "Systems" },
  "nav.admin": { ar: "الإدارة", en: "Management" },
  "nav.dashboard": { ar: "مركز القيادة", en: "Command Center" },
  "nav.campaigns": { ar: "الحملات", en: "Campaigns" },
  "nav.leads": { ar: "العملاء المحتملون", en: "Leads" },
  "nav.research": { ar: "مهام البحث", en: "Research" },
  "nav.chat": { ar: "المساعد الذكي", en: "AI Assistant" },
  "nav.review": { ar: "لوحة المراجعة", en: "Review Panel" },
  "nav.verify": { ar: "فحص الإيميل", en: "Email Verifier" },
  "nav.analytics": { ar: "التحليلات", en: "Analytics" },
  "nav.activity": { ar: "سجل النشاط", en: "Activity Log" },
  "nav.agents": { ar: "الوكلاء", en: "Agents" },
  "nav.integrations": { ar: "التكاملات", en: "Integrations" },
  "nav.icp": { ar: "معايير الفلترة (ICP)", en: "ICP Criteria" },
  "nav.keys": { ar: "الاستهلاك والمفاتيح", en: "Keys & Quotas" },
  "nav.config": { ar: "الإعدادات", en: "Settings" },

  // Common Actions
  "action.search": { ar: "بحث...", en: "Search..." },
  "action.export_csv": { ar: "تنزيل CSV", en: "Export CSV" },
  "action.export_instantly": { ar: "تصدير Instantly / Smartlead", en: "Export Instantly / Smartlead" },
  "action.export_webhook": { ar: "إرسال إلى Webhook", en: "Push to Webhook" },
  "action.verify": { ar: "فحص الإيميلات", en: "Verify Emails" },
  "action.filter": { ar: "تصفية", en: "Filter" },
  "action.save": { ar: "حفظ", en: "Save" },
  "action.cancel": { ar: "إلغاء", en: "Cancel" },

  // Statuses
  "status.accepted": { ar: "مقبول", en: "Accepted" },
  "status.review": { ar: "مراجعة", en: "Review" },
  "status.rejected": { ar: "مرفوض", en: "Rejected" },
  "status.total": { ar: "إجمالي", en: "Total" },
};

const LanguageContext = createContext<LanguageContextType | undefined>(undefined);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Language>(() => {
    return (localStorage.getItem("leadEngine.lang") as Language) || "ar";
  });

  const dir = lang === "ar" ? "rtl" : "ltr";

  const setLang = (nextLang: Language) => {
    setLangState(nextLang);
    localStorage.setItem("leadEngine.lang", nextLang);
  };

  const toggleLang = () => {
    setLang(lang === "ar" ? "en" : "ar");
  };

  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = dir;
  }, [lang, dir]);

  const t = (key: string): string => {
    const entry = DICTIONARY[key];
    if (!entry) return key;
    return entry[lang] ?? key;
  };

  return (
    <LanguageContext.Provider value={{ lang, setLang, toggleLang, dir, t }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage() {
  const context = useContext(LanguageContext);
  if (!context) {
    // Graceful fallback if used outside provider
    return {
      lang: "ar" as Language,
      setLang: () => {},
      toggleLang: () => {},
      dir: "rtl" as const,
      t: (k: string) => k,
    };
  }
  return context;
}
