// Bilingual dictionary for Lead Engine. Keys map to { ar, en }.
// `t(key)` reads the current language from the store context.

export const dict = {
  "app.name": { ar: "Lead Engine", en: "Lead Engine" },
  "app.tagline": { ar: "بحوث العملاء المدعومة بالذكاء الاصطناعي", en: "AI-Powered Lead Research" },

  // nav
  "nav.commandCenter": { ar: "مركز القيادة", en: "Command Center" },
  "nav.research": { ar: "البحث", en: "Research" },
  "nav.chat": { ar: "الشات", en: "Chat" },
  "nav.jobs": { ar: "وظائف البحث", en: "Research Jobs" },
  "nav.icp": { ar: "ICP", en: "ICP" },
  "nav.leads": { ar: "العملاء", en: "Leads" },
  "nav.allLeads": { ar: "كل العملاء", en: "All Leads" },
  "nav.review": { ar: "قائمة المراجعة", en: "Review Queue" },
  "nav.intelligence": { ar: "الذكاء", en: "Intelligence" },
  "nav.analytics": { ar: "التحليلات", en: "Analytics" },
  "nav.activity": { ar: "النشاط", en: "Activity" },
  "nav.system": { ar: "النظام", en: "System" },
  "nav.providers": { ar: "المزودون", en: "Providers" },
  "nav.credentials": { ar: "بيانات الاعتماد", en: "Credentials" },
  "nav.integrations": { ar: "التكاملات", en: "Integrations" },
  "nav.admin": { ar: "الإدارة", en: "Admin" },
  "nav.agents": { ar: "الوكلاء", en: "Agents" },
  "nav.organization": { ar: "المؤسسة", en: "Organization" },
  "nav.settings": { ar: "الإعدادات", en: "Settings" },

  // common
  "common.startResearch": { ar: "ابدأ بحثًا", en: "Start Research" },
  "common.search": { ar: "بحث", en: "Search" },
  "common.filters": { ar: "تصفية", en: "Filters" },
  "common.all": { ar: "الكل", en: "All" },
  "common.lastUpdated": { ar: "آخر تحديث", en: "Last updated" },
  "common.viewDetails": { ar: "عرض التفاصيل", en: "View details" },
  "common.open": { ar: "فتح", en: "Open" },
  "common.cancel": { ar: "إلغاء", en: "Cancel" },
  "common.send": { ar: "إرسال", en: "Send" },
  "common.close": { ar: "إغلاق", en: "Close" },
  "common.comingSoon": { ar: "قريبًا", en: "Coming Soon" },
  "common.unsupported": { ar: "غير مدعوم بعد", en: "Not supported yet" },
  "common.confidence": { ar: "الثقة", en: "Confidence" },
  "common.evidenceCoverage": { ar: "تغطية الأدلة", en: "Evidence coverage" },

  // command center
  "cc.title": { ar: "مركز القيادة", en: "Command Center" },
  "cc.subtitle": { ar: "ماذا يحدث الآن، وما الذي يحتاج تدخلك.", en: "What's happening now, and what needs your input." },
  "cc.activeResearch": { ar: "أبحاث نشطة", en: "Active Research" },
  "cc.readyForReview": { ar: "جاهزة للمراجعة", en: "Ready for Review" },
  "cc.recentResults": { ar: "نتائج حديثة", en: "Recent Results" },
  "cc.systemHealth": { ar: "صحة النظام", en: "System Health" },
  "cc.usage": { ar: "الاستخدام", en: "Usage" },
  "cc.actionCenter": { ar: "مركز الإجراءات", en: "Action Center" },

  // chat
  "chat.placeholder": { ar: "صف العميل المثالي الذي تريد الوصول إليه…", en: "Describe the ideal customer you want to reach…" },
  "chat.title": { ar: "شات البحث", en: "Research Chat" },
  "chat.subtitle": { ar: "وصف الهدف، والنظام يتولى البحث والتحقق.", en: "Describe your goal — the system researches and verifies." },
  "chat.agentStatus": { ar: "حالة الوكيل", en: "Agent status" },
  "chat.researchProgress": { ar: "تقدّم البحث", en: "Research progress" },
  "chat.agentActions": { ar: "إجراءات الوكيل", en: "Agent actions" },
  "chat.discovered": { ar: "مرشح مكتشف", en: "candidates discovered" },
  "chat.deduplicated": { ar: "بعد إزالة التكرار", en: "after deduplication" },
  "chat.researched": { ar: "تم البحث عنها", en: "researched" },
  "chat.verified": { ar: "تم التحقق", en: "verified" },
  "chat.qualified": { ar: "مؤهلة", en: "qualified" },
  "chat.readyForReview": { ar: "جاهزة للمراجعة", en: "ready for review" },
  "chat.openReviewQueue": { ar: "افتح قائمة المراجعة", en: "Open Review Queue" },

  // review
  "review.title": { ar: "قائمة المراجعة", en: "Review Queue" },
  "review.subtitle": { ar: "القرار النهائي للإنسان. الحدود تنتهي عند اعتماد جهة الاتصال.", en: "Human final decision. The boundary ends at approving contact." },
  "review.approve": { ar: "اعتماد جهة اتصال", en: "Approve Contact" },
  "review.reject": { ar: "رفض", en: "Reject" },
  "review.researchMore": { ar: "ابحث أكثر", en: "Research More" },
  "review.saveLater": { ar: "احفظ لاحقًا", en: "Save for Later" },
  "review.decisionNote": { ar: "ملاحظة القرار (اختياري)", en: "Decision note (optional)" },
  "review.noSend": { ar: "لا يوجد إرسال تلقائي — النظام لا يراسل أي جهة اتصال.", en: "No automatic sending — the system never contacts anyone." },

  // lead detail
  "ld.whyLead": { ar: "لماذا هذا العميل المحتمل؟", en: "Why this lead" },
  "ld.icpFit": { ar: "مدى المطابقة لـICP", en: "ICP Fit" },
  "ld.contact": { ar: "جهة الاتصال", en: "Contact" },
  "ld.revealPii": { ar: "كشف بيانات الاتصال", en: "Reveal contact details" },
  "ld.piiReason": { ar: "سبب الكشف", en: "Reveal reason" },
  "ld.facts": { ar: "الحقائق", en: "Facts" },
  "ld.evidence": { ar: "الأدلة والمصادر", en: "Evidence & Sources" },
  "ld.conflicts": { ar: "التعارضات", en: "Conflicts" },
  "ld.timeline": { ar: "مسار البحث", en: "Research Timeline" },
  "ld.decision": { ar: "القرار", en: "Decision" },
  "ld.summary": { ar: "ملخص", en: "Summary" },

  // jobs
  "jobs.title": { ar: "وظائف البحث", en: "Research Jobs" },
  "jobs.objective": { ar: "الهدف", en: "Objective" },
  "jobs.status": { ar: "الحالة", en: "Status" },
  "jobs.progress": { ar: "التقدّم", en: "Progress" },
  "jobs.budget": { ar: "الميزانية", en: "Budget" },
  "jobs.stopReason": { ar: "سبب التوقف", en: "Stop reason" },
  "jobs.timeline": { ar: "الخط الزمني", en: "Timeline" },
  "jobs.stages": { ar: "المراحل", en: "Stages" },
  "jobs.providers": { ar: "نشاط المزودين", en: "Provider activity" },

  // icp
  "icp.title": { ar: "معايير العميل المثالي", en: "Ideal Customer Profile" },
  "icp.current": { ar: "الحالية", en: "Current" },
  "icp.versions": { ar: "النسخ", en: "Versions" },
  "icp.createdBy": { ar: "أنشأها", en: "Created by" },
  "icp.changes": { ar: "التغييرات", en: "Changes" },

  // system
  "providers.title": { ar: "المزودون والموارد", en: "Providers & Resources" },
  "providers.why": { ar: "لماذا استخدم النظام هذا المزود؟", en: "Why did the system use this provider?" },
  "creds.title": { ar: "بيانات الاعتماد", en: "Credentials" },
  "creds.noSecret": { ar: "تُخفى المفاتيح بعد الحفظ ولا تظهر مرة أخرى.", en: "Keys are hidden after saving and never shown again." },
  "integrations.title": { ar: "التكاملات", en: "Integrations" },
  "agents.title": { ar: "وحدة عمليات الذكاء", en: "AI Operations Console" },
  "agents.capabilityNote": { ar: "امتلاك الأداة لا يعني الإذن باستخدامها — القرارات الحساسة للإنسان فقط.", en: "Having a tool is not permission to use it — sensitive decisions stay with people." },
  "activity.title": { ar: "سجل النشاط والتدقيق", en: "Activity & Audit Log" },
  "analytics.title": { ar: "التحليلات", en: "Analytics" },
  "settings.title": { ar: "الإعدادات", en: "Settings" },

  // empty
  "empty.leads": { ar: "لم تنشئ أي عملية بحث بعد.", en: "You haven't run any research yet." },
  "empty.review": { ar: "لا يوجد عملاء بانتظار مراجعتك الآن.", en: "No leads are waiting for your review." },
  "empty.integrations": { ar: "لم يتم ربط أي تكامل بعد.", en: "No integrations connected yet." },
};

// timeline / chat-status codes stored in data → human labels
export const EVENT_LABELS = {
  "Job created": { ar: "إنشاء الوظيفة", en: "Job created" },
  "Understanding intent": { ar: "فهم الهدف", en: "Understanding intent" },
  "Waiting for user": { ar: "بانتظار إجابتك", en: "Waiting for you" },
  "User answered": { ar: "تمت الإجابة", en: "You answered" },
  "Defining ICP": { ar: "تثبيت ICP", en: "ICP set" },
  Discovery: { ar: "الاكتشاف", en: "Discovery" },
  Deduplication: { ar: "إزالة التكرار", en: "Deduplication" },
  Research: { ar: "البحث", en: "Research" },
  Verification: { ar: "التحقق", en: "Verification" },
  Qualification: { ar: "التأهيل", en: "Qualification" },
  "Ready for review": { ar: "جاهزة للمراجعة", en: "Ready for review" },
  "Review completed": { ar: "اكتملت المراجعة", en: "Review completed" },
  Review: { ar: "المراجعة", en: "Review" },
  Paused: { ar: "إيقاف مؤقت", en: "Paused" },
  Resumed: { ar: "استئناف", en: "Resumed" },
  Cancelled: { ar: "إلغاء", en: "Cancelled" },
  "Policy block": { ar: "حظر سياسة", en: "Policy block" },
  "Research more": { ar: "بحث إضافي", en: "Research more" },
  "Re-qualified": { ar: "إعادة التأهيل", en: "Re-qualified" },
  discovered: { ar: "الاكتشاف", en: "Discovery" },
  deduplicated: { ar: "إزالة التكرار", en: "Deduplication" },
  researched: { ar: "البحث", en: "Research" },
  verified: { ar: "التحقق", en: "Verification" },
  qualified: { ar: "التأهيل", en: "Qualification" },
  readyForReview: { ar: "جاهزة للمراجعة", en: "Ready for review" },
};
export const eventLabel = (e, lang) => EVENT_LABELS[e]?.[lang] || e;

export const CHAT_STATUS = {
  "Understanding request": { ar: "يفهم الطلب", en: "Understanding request" },
  "Defining ICP": { ar: "يثبّت ICP", en: "Setting ICP" },
  "Waiting for review": { ar: "بانتظار المراجعة", en: "Waiting for review" },
};
export const chatStatusLabel = (s, lang) => CHAT_STATUS[s]?.[lang] || s;

export function makeT(lang) {
  return (key) => {
    const entry = dict[key];
    if (!entry) return key;
    return entry[lang] || entry.ar || key;
  };
}