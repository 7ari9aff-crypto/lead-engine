// Lead Engine — demo data seed.
// All data here is realistic mock data for the frontend simulation.

export const STATUSES = {
  // job statuses
  QUEUED: "QUEUED",
  RUNNING: "RUNNING",
  DISCOVERING: "DISCOVERING",
  RESEARCHING: "RESEARCHING",
  VERIFYING: "VERIFYING",
  QUALIFYING: "QUALIFYING",
  READY_FOR_REVIEW: "READY_FOR_REVIEW",
  COMPLETED: "COMPLETED",
  PAUSED: "PAUSED",
  WAITING_FOR_USER: "WAITING_FOR_USER",
  CANCELLED: "CANCELLED",
  FAILED: "FAILED",
  // lead statuses
  IN_RESEARCH: "IN_RESEARCH",
  APPROVED: "APPROVED",
  REJECTED: "REJECTED",
  SAVED: "SAVED",
  // fact verification states
  VERIFIED: "VERIFIED",
  CONFLICTED: "CONFLICTED",
  STALE: "STALE",
  UNVERIFIED: "UNVERIFIED",
  INFERRED: "INFERRED",
};

export const STOP_REASONS = {
  NO_CANDIDATES: "NO_CANDIDATES",
  BUDGET_EXHAUSTED: "BUDGET_EXHAUSTED",
  PROVIDER_UNAVAILABLE: "PROVIDER_UNAVAILABLE",
  WAITING_FOR_USER: "WAITING_FOR_USER",
  POLICY_BLOCK: "POLICY_BLOCK",
  SYSTEM_FAILURE: "SYSTEM_FAILURE",
  COMPLETED: "COMPLETED",
  CANCELLED: "CANCELLED",
};

const now = () => new Date();
const minsAgo = (m) => new Date(Date.now() - m * 60000).toISOString();
const hoursAgo = (h) => new Date(Date.now() - h * 3600000).toISOString();
const daysAgo = (d) => new Date(Date.now() - d * 86400000).toISOString();

export const icps = [
  {
    id: "icp_3",
    version: 3,
    label: "ICP v3",
    isCurrent: true,
    createdBy: "Noura Al-Otaibi",
    createdAt: daysAgo(5),
    changes: "حصر الموقع في الرياض، وتضييق الحجم إلى 20–200 موظف، واشتراط وجود فريق مبيعات، وإضافة «برمجيات مؤسسية» و«CRM» كنية شراء.",
    criteria: {
      industry: ["SaaS", "برمجيات مؤسسية"],
      location: "الرياض، السعودية",
      companySize: "20–200 موظف",
      businessModel: "B2B",
      hasSalesTeam: true,
      websiteRequired: true,
      intent: ["أتمتة المبيعات", "CRM"],
    },
  },
  {
    id: "icp_2",
    version: 2,
    label: "ICP v2",
    isCurrent: false,
    createdBy: "Noura Al-Otaibi",
    createdAt: daysAgo(12),
    changes: "حصر القطاع في SaaS والسوق في السعودية، وتحديد الحجم بين 10 و500 موظف.",
    criteria: {
      industry: ["SaaS"],
      location: "السعودية",
      companySize: "10–500 موظف",
      businessModel: "B2B",
      hasSalesTeam: false,
      websiteRequired: true,
      intent: ["أتمتة المبيعات"],
    },
  },
  {
    id: "icp_1",
    version: 1,
    label: "ICP v1",
    isCurrent: false,
    createdBy: "Khalid Al-Harbi",
    createdAt: daysAgo(30),
    changes: "النسخة الأولى — معايير استهداف عامة.",
    criteria: {
      industry: ["تقنية"],
      location: "دول الخليج",
      companySize: "غير محدد",
      businessModel: "B2B / B2C",
      hasSalesTeam: false,
      websiteRequired: false,
      intent: [],
    },
  },
];

// ICP fit = weighted share of criteria matched (yes = full, partial = half)
export const CRITERIA_WEIGHTS = { "القطاع": 25, "الموقع": 25, "حجم الشركة": 20, "النموذج": 15, "فريق المبيعات": 15 };
export function scoreFromCriteria(criteria) {
  let got = 0, total = 0;
  criteria.forEach((c) => {
    const w = CRITERIA_WEIGHTS[c.name] ?? 10;
    total += w;
    got += c.match === "yes" ? w : c.match === "partial" ? w / 2 : 0;
  });
  return total ? Math.round((got / total) * 100) : 0;
}
// lead-level verification follows its facts
export function deriveVerification(facts = []) {
  if (facts.some((f) => f.status === "CONFLICTED")) return "CONFLICTED";
  if (facts.some((f) => f.status !== "VERIFIED")) return "PARTIALLY_VERIFIED";
  return "VERIFIED";
}
// evaluate a discovered company against the current ICP (used for chat-driven research)
export function evaluateCandidate(c) {
  const sizeOk = c.size >= 20 && c.size <= 200;
  return [
    { name: "القطاع", value: c.industry, match: c.industry === "SaaS" ? "yes" : /SaaS|برمج/.test(c.industry) ? "partial" : "no", expected: "SaaS" },
    { name: "الموقع", value: c.location, match: c.location.includes("الرياض") ? "yes" : "no", expected: "الرياض" },
    { name: "حجم الشركة", value: `${c.size} موظف`, match: sizeOk ? "yes" : "no", expected: "20–200" },
    { name: "النموذج", value: c.businessModel, match: c.businessModel === "B2B" ? "yes" : "no", expected: "B2B" },
    { name: "فريق المبيعات", value: c.hasSalesTeam === true ? "نعم" : c.hasSalesTeam === false ? "لا" : "غير مؤكد", match: c.hasSalesTeam === true ? "yes" : c.hasSalesTeam === false ? "no" : "partial", expected: "نعم" },
  ];
}

// reusable lead builder
function lead(p) {
  return {
    id: p.id,
    company: {
      name: p.company.name,
      domain: p.company.domain,
      location: p.company.location,
      industry: p.company.industry,
      size: p.company.size,
      sizeRange: p.company.sizeRange,
      website: p.company.website,
      founded: p.company.founded,
      businessModel: p.company.businessModel,
      hasSalesTeam: p.company.hasSalesTeam,
      description: p.company.description,
    },
    contact: {
      name: p.contact.name,
      title: p.contact.title,
      email: p.contact.email,
      phone: p.contact.phone,
      linkedin: p.contact.linkedin,
      piiAccessed: false,
      revealReason: null,
      revealAt: null,
    },
    icpFit: {
      score: scoreFromCriteria(p.icpFit.criteria),
      criteria: p.icpFit.criteria,
    },
    status: p.status,
    verificationStatus: deriveVerification(p.facts),
    evidenceCoverage: p.evidenceCoverage,
    confidence: p.confidence,
    lastUpdated: p.lastUpdated,
    jobId: p.jobId,
    icpVersion: p.icpVersion,
    facts: p.facts,
    conflicts: p.conflicts || [],
    evidence: p.evidence,
    timeline: p.timeline,
    reviewDecision: null,
    reviewNote: null,
    reviewAt: null,
  };
}

export const seedLeads = [
  lead({
    id: "lead_1",
    company: {
      name: "Nusuk Tech",
      domain: "nusuk.tech",
      location: "الرياض، السعودية",
      industry: "SaaS",
      size: 84,
      sizeRange: "50–200",
      website: "https://nusuk.tech",
      founded: 2019,
      businessModel: "B2B",
      hasSalesTeam: true,
      description: "منصة SaaS لإدارة تجربة الحجاج والزيارة، تبيع لشركات السياحة والطيران.",
    },
    contact: {
      name: "م. سارة المطيري",
      title: "VP of Sales",
      email: "s.almutairi@nusuk.tech",
      phone: "+966 5X XXX 4488",
      linkedin: "linkedin.com/in/salmutairi",
    },
    icpFit: {
      score: 87,
      criteria: [
        { name: "القطاع", value: "SaaS", match: "yes", expected: "SaaS" },
        { name: "الموقع", value: "الرياض", match: "yes", expected: "الرياض" },
        { name: "حجم الشركة", value: "84 موظف", match: "yes", expected: "20–200" },
        { name: "النموذج", value: "B2B", match: "yes", expected: "B2B" },
        { name: "فريق المبيعات", value: "غير مؤكد", match: "partial", expected: "نعم" },
      ],
    },
    status: "READY_FOR_REVIEW",
    verificationStatus: "VERIFIED",
    evidenceCoverage: 92,
    confidence: "عالية",
    lastUpdated: minsAgo(35),
    jobId: "job_1",
    icpVersion: 3,
    facts: [
      { property: "اسم الشركة", value: "Nusuk Tech", status: "VERIFIED", source: "الموقع الرسمي + السجل التجاري", collectedAt: hoursAgo(3), freshness: "طازج (3 ساعات)" },
      { property: "عدد الموظفين", value: "84", status: "CONFLICTED", source: "LinkedIn + Bloomberg", collectedAt: hoursAgo(2), freshness: "طازج (ساعتان)" },
      { property: "الموقع الجغرافي", value: "الرياض", status: "VERIFIED", source: "Google Maps", collectedAt: hoursAgo(3), freshness: "طازج" },
      { property: "الموقع الإلكتروني", value: "nusuk.tech", status: "VERIFIED", source: "WHOIS + فحص مباشر", collectedAt: hoursAgo(3), freshness: "طازج" },
      { property: "فريق المبيعات", value: "محتمل (3 أعضاء بلقب Sales)", status: "INFERRED", source: "LinkedIn", collectedAt: hoursAgo(2), freshness: "طازج" },
      { property: "النموذج", value: "B2B", status: "VERIFIED", source: "الموقع الرسمي", collectedAt: hoursAgo(3), freshness: "طازج" },
    ],
    conflicts: [
      {
        property: "عدد الموظفين",
        sources: [
          { source: "LinkedIn", value: "84" },
          { source: "Bloomberg", value: "120" },
        ],
      },
    ],
    evidence: [
      { claim: "شركة SaaS في الرياض", sources: ["الموقع الرسمي", "Crunchbase"] },
      { claim: "تمتلك موقعًا رسميًا فعالًا", sources: ["فحص HTTP 200", "WHOIS"] },
      { claim: "تبيع نموذج B2B", sources: ["صفحة التسعير", "صفحة العملاء"] },
    ],
    timeline: [
      { at: hoursAgo(3), event: "Discovery", detail: "تم اكتشاف الشركة من Exa search" },
      { at: hoursAgo(2), event: "Research", detail: "جمع 6 حقائق من 4 مصادر" },
      { at: minsAgo(110), event: "Verification", detail: "5 من 6 حقائق تم التحقق منها" },
      { at: minsAgo(35), event: "Qualification", detail: "ICP Fit = 93% — جاهز للمراجعة" },
    ],
  }),
  lead({
    id: "lead_2",
    company: {
      name: "Madar Logistics",
      domain: "madarlog.sa",
      location: "جدة، السعودية",
      industry: "لوجستيات / SaaS",
      size: 140,
      sizeRange: "50–200",
      website: "https://madarlog.sa",
      founded: 2017,
      businessModel: "B2B",
      hasSalesTeam: true,
      description: "منصة SaaS لإدارة سلاسل التوريد، عملاء من قطاع التجزئة والتصنيع.",
    },
    contact: {
      name: "أ. فهد الزهراني",
      title: "Head of Growth",
      email: "f.zahrani@madarlog.sa",
      phone: "+966 5X XXX 9921",
      linkedin: "linkedin.com/in/fahadz",
    },
    icpFit: {
      score: 78,
      criteria: [
        { name: "القطاع", value: "لوجستيات / SaaS", match: "partial", expected: "SaaS" },
        { name: "الموقع", value: "جدة", match: "no", expected: "الرياض" },
        { name: "حجم الشركة", value: "140 موظف", match: "yes", expected: "20–200" },
        { name: "النموذج", value: "B2B (غير موثّق)", match: "partial", expected: "B2B" },
        { name: "فريق المبيعات", value: "نعم", match: "yes", expected: "نعم" },
      ],
    },
    status: "READY_FOR_REVIEW",
    verificationStatus: "PARTIALLY_VERIFIED",
    evidenceCoverage: 68,
    confidence: "متوسطة",
    lastUpdated: minsAgo(90),
    jobId: "job_1",
    icpVersion: 3,
    facts: [
      { property: "اسم الشركة", value: "Madar Logistics", status: "VERIFIED", source: "السجل التجاري", collectedAt: hoursAgo(5), freshness: "حديث (5 ساعات)" },
      { property: "عدد الموظفين", value: "140", status: "VERIFIED", source: "LinkedIn", collectedAt: hoursAgo(5), freshness: "حديث" },
      { property: "الموقع الجغرافي", value: "جدة", status: "VERIFIED", source: "Google Maps", collectedAt: hoursAgo(5), freshness: "حديث" },
      { property: "فريق المبيعات", value: "نعم", status: "VERIFIED", source: "LinkedIn", collectedAt: hoursAgo(4), freshness: "حديث" },
      { property: "نموذج الإيراد", value: "B2B", status: "UNVERIFIED", source: "—", collectedAt: hoursAgo(4), freshness: "غير مؤكد" },
    ],
    conflicts: [],
    evidence: [
      { claim: "تمتلك فريق مبيعات", sources: ["LinkedIn (4 أعضاء بلقب Sales)"] },
      { claim: "حجم الشركة ضمن النطاق", sources: ["LinkedIn"] },
    ],
    timeline: [
      { at: hoursAgo(5), event: "Discovery", detail: "اكتشاف من Exa" },
      { at: hoursAgo(4), event: "Research", detail: "5 حقائق من مصدرين" },
      { at: minsAgo(90), event: "Qualification", detail: "ICP Fit = 55%" },
    ],
  }),
  lead({
    id: "lead_3",
    company: {
      name: "Sahl Pay",
      domain: "sahlpay.io",
      location: "الرياض، السعودية",
      industry: "Fintech SaaS",
      size: 32,
      sizeRange: "20–50",
      website: "https://sahlpay.io",
      founded: 2021,
      businessModel: "B2B2C",
      hasSalesTeam: false,
      description: "منصة دفع B2B2C تستهدف الشركات الصغيرة.",
    },
    contact: {
      name: "غير محدد بعد",
      title: "—",
      email: "—",
      phone: "—",
      linkedin: "—",
    },
    icpFit: {
      score: 64,
      criteria: [
        { name: "القطاع", value: "Fintech SaaS", match: "partial", expected: "SaaS" },
        { name: "الموقع", value: "الرياض", match: "yes", expected: "الرياض" },
        { name: "حجم الشركة", value: "32 موظف", match: "yes", expected: "20–200" },
        { name: "النموذج", value: "B2B2C", match: "no", expected: "B2B" },
        { name: "فريق المبيعات", value: "لا", match: "no", expected: "نعم" },
      ],
    },
    status: "READY_FOR_REVIEW",
    verificationStatus: "PARTIALLY_VERIFIED",
    evidenceCoverage: 54,
    confidence: "منخفضة",
    lastUpdated: hoursAgo(3),
    jobId: "job_1",
    icpVersion: 3,
    facts: [
      { property: "اسم الشركة", value: "Sahl Pay", status: "VERIFIED", source: "الموقع الرسمي", collectedAt: hoursAgo(6), freshness: "حديث" },
      { property: "عدد الموظفين", value: "32", status: "STALE", source: "Crunchbase (2023)", collectedAt: daysAgo(400), freshness: "قديم (أكثر من سنة)" },
      { property: "الموقع الجغرافي", value: "الرياض", status: "VERIFIED", source: "Google Maps", collectedAt: hoursAgo(6), freshness: "حديث" },
      { property: "فريق المبيعات", value: "غير موجود", status: "INFERRED", source: "LinkedIn", collectedAt: hoursAgo(5), freshness: "حديث" },
    ],
    conflicts: [],
    evidence: [
      { claim: "تقع في الرياض", sources: ["Google Maps", "صفحة تواصل معنا"] },
    ],
    timeline: [
      { at: hoursAgo(6), event: "Discovery", detail: "اكتشاف من Gemini search" },
      { at: hoursAgo(5), event: "Research", detail: "4 حقائق، 2 منها تحتاج تحديث" },
      { at: hoursAgo(3), event: "Qualification", detail: "ICP Fit = 57% — توصية: رفض أو بحث إضافي" },
    ],
  }),
  lead({
    id: "lead_4",
    company: {
      name: "Thiqa Cloud",
      domain: "thiqa.cloud",
      location: "الرياض، السعودية",
      industry: "SaaS",
      size: 96,
      sizeRange: "50–200",
      website: "https://thiqa.cloud",
      founded: 2018,
      businessModel: "B2B",
      hasSalesTeam: true,
      description: "منصة سحابية لإدارة البنية التحتية، عملاء مؤسسيون.",
    },
    contact: {
      name: "د. ريم العنزي",
      title: "Chief Revenue Officer",
      email: "r.alanazi@thiqa.cloud",
      phone: "+966 5X XXX 7730",
      linkedin: "linkedin.com/in/reemanazi",
    },
    icpFit: {
      score: 91,
      criteria: [
        { name: "القطاع", value: "SaaS", match: "yes", expected: "SaaS" },
        { name: "الموقع", value: "الرياض", match: "yes", expected: "الرياض" },
        { name: "حجم الشركة", value: "96 موظف", match: "yes", expected: "20–200" },
        { name: "النموذج", value: "B2B", match: "yes", expected: "B2B" },
        { name: "فريق المبيعات", value: "نعم", match: "yes", expected: "نعم" },
      ],
    },
    status: "APPROVED",
    verificationStatus: "VERIFIED",
    evidenceCoverage: 96,
    confidence: "عالية",
    lastUpdated: daysAgo(1),
    jobId: "job_2",
    icpVersion: 3,
    facts: [
      { property: "اسم الشركة", value: "Thiqa Cloud", status: "VERIFIED", source: "الموقع + السجل التجاري", collectedAt: daysAgo(2), freshness: "حديث" },
      { property: "عدد الموظفين", value: "96", status: "VERIFIED", source: "LinkedIn + ZoomInfo", collectedAt: daysAgo(2), freshness: "حديث" },
      { property: "الموقع الجغرافي", value: "الرياض", status: "VERIFIED", source: "Google Maps", collectedAt: daysAgo(2), freshness: "حديث" },
      { property: "فريق المبيعات", value: "نعم (8 أعضاء)", status: "VERIFIED", source: "LinkedIn", collectedAt: daysAgo(2), freshness: "حديث" },
      { property: "النموذج", value: "B2B", status: "VERIFIED", source: "الموقع الرسمي", collectedAt: daysAgo(2), freshness: "حديث" },
      { property: "صانع القرار", value: "د. ريم العنزي — CRO", status: "VERIFIED", source: "LinkedIn + الموقع", collectedAt: daysAgo(2), freshness: "حديث" },
    ],
    conflicts: [],
    evidence: [
      { claim: "تطابق كامل مع ICP", sources: ["5 مصادر متقاطعة"] },
      { claim: "صانع قرار محدد", sources: ["LinkedIn", "صفحة الفريق"] },
    ],
    timeline: [
      { at: daysAgo(2), event: "Discovery", detail: "اكتشاف من Exa" },
      { at: daysAgo(2), event: "Verification", detail: "6/6 حقائق متحققة" },
      { at: daysAgo(1), event: "Review", detail: "تمت الموافقة من قبل Noura" },
    ],
    reviewDecision: "APPROVED",
    reviewAt: daysAgo(1),
  }),
  lead({
    id: "lead_5",
    company: {
      name: "Bayan Analytics",
      domain: "bayan.io",
      location: "دبي، الإمارات",
      industry: "SaaS",
      size: 210,
      sizeRange: "200+",
      website: "https://bayan.io",
      founded: 2016,
      businessModel: "B2B",
      hasSalesTeam: true,
      description: "منصة تحليلات بيانات.",
    },
    contact: { name: "—", title: "—", email: "—", phone: "—", linkedin: "—" },
    icpFit: {
      score: 42,
      criteria: [
        { name: "القطاع", value: "SaaS", match: "yes", expected: "SaaS" },
        { name: "الموقع", value: "دبي", match: "no", expected: "الرياض" },
        { name: "حجم الشركة", value: "210 موظف", match: "no", expected: "20–200" },
        { name: "النموذج", value: "B2B", match: "yes", expected: "B2B" },
        { name: "فريق المبيعات", value: "نعم", match: "yes", expected: "نعم" },
      ],
    },
    status: "REJECTED",
    verificationStatus: "VERIFIED",
    evidenceCoverage: 80,
    confidence: "عالية",
    lastUpdated: daysAgo(3),
    jobId: "job_2",
    icpVersion: 3,
    facts: [
      { property: "اسم الشركة", value: "Bayan Analytics", status: "VERIFIED", source: "Crunchbase", collectedAt: daysAgo(4), freshness: "حديث" },
      { property: "الموقع الجغرافي", value: "دبي", status: "VERIFIED", source: "Google Maps", collectedAt: daysAgo(4), freshness: "حديث" },
      { property: "عدد الموظفين", value: "210", status: "VERIFIED", source: "LinkedIn", collectedAt: daysAgo(4), freshness: "حديث" },
    ],
    conflicts: [],
    evidence: [{ claim: "خارج النطاق الجغرافي والحد الأقصى للحجم", sources: ["LinkedIn", "Google Maps"] }],
    timeline: [
      { at: daysAgo(4), event: "Discovery", detail: "اكتشاف من Exa" },
      { at: daysAgo(3), event: "Review", detail: "مرفوضة — خارج الرياض وحجم أكبر من الحد" },
    ],
    reviewDecision: "REJECTED",
    reviewAt: daysAgo(3),
  }),
];

export const seedJobs = [
  {
    id: "job_1",
    objective: "شركات SaaS في الرياض بين 20 و200 موظف، يحتمل أن تحتاج أداة أتمتة للمبيعات.",
    icpVersion: 3,
    status: "READY_FOR_REVIEW",
    createdById: "u_noura",
    createdByName: "Noura Al-Otaibi",
    createdAt: hoursAgo(6),
    startedAt: hoursAgo(6),
    completedAt: minsAgo(18),
    stages: { discovered: 42, deduplicated: 31, researched: 18, verified: 14, qualified: 6, readyForReview: 3 },
    budget: { used: 1280, limit: 2000, unit: "نقطة" },
    stopReason: "COMPLETED",
    timeline: [
      { at: hoursAgo(6), event: "Job created", detail: "تم إنشاء وظيفة البحث بناءً على ICP v3" },
      { at: hoursAgo(5), event: "Discovery", detail: "اكتشاف 42 مرشح من Exa + Gemini" },
      { at: hoursAgo(4), event: "Deduplication", detail: "31 بعد إزالة التكرار" },
      { at: hoursAgo(3), event: "Research", detail: "بحث معمق لـ 18 شركة" },
      { at: hoursAgo(2), event: "Verification", detail: "التحقق من 14 شركة" },
      { at: minsAgo(120), event: "Qualification", detail: "6 شركات مؤهلة" },
      { at: minsAgo(18), event: "Ready for review", detail: "3 عملاء جاهزون للمراجعة" },
    ],
    providerActivity: [
      { provider: "Exa", action: "Discovery — 24 مرشح", at: hoursAgo(5) },
      { provider: "Gemini Search", action: "Discovery — 18 مرشح", at: hoursAgo(5) },
      { provider: "LinkedIn", action: "Research — بيانات الموظفين", at: hoursAgo(3) },
      { provider: "Google Maps", action: "Verification — المواقع", at: hoursAgo(2) },
    ],
    leadIds: ["lead_1", "lead_2", "lead_3"],
  },
  {
    id: "job_2",
    objective: "شركات B2B SaaS في السعودية فوق 20 موظف مع فريق مبيعات.",
    icpVersion: 3,
    status: "COMPLETED",
    createdById: "u_noura",
    createdByName: "Noura Al-Otaibi",
    createdAt: daysAgo(3),
    startedAt: daysAgo(3),
    completedAt: daysAgo(2),
    stages: { discovered: 55, deduplicated: 38, researched: 22, verified: 19, qualified: 4, readyForReview: 2 },
    budget: { used: 1900, limit: 2000, unit: "نقطة" },
    stopReason: "COMPLETED",
    timeline: [
      { at: daysAgo(3), event: "Job created", detail: "ICP v3" },
      { at: daysAgo(2), event: "Ready for review", detail: "عميلان جاهزان للمراجعة" },
      { at: daysAgo(1), event: "Review completed", detail: "تمت مراجعة كل العملاء" },
    ],
    providerActivity: [
      { provider: "Exa", action: "Discovery", at: daysAgo(3) },
      { provider: "ZoomInfo", action: "Research — جهات الاتصال", at: daysAgo(3) },
    ],
    leadIds: ["lead_4", "lead_5"],
  },
  {
    id: "job_3",
    objective: "شركات برمجيات مؤسسية في الرياض قد تحتاج CRM جديد.",
    icpVersion: 3,
    status: "WAITING_FOR_USER",
    createdById: "u_khalid",
    createdByName: "Khalid Al-Harbi",
    createdAt: minsAgo(40),
    startedAt: minsAgo(40),
    completedAt: null,
    stages: { discovered: 0, deduplicated: 0, researched: 0, verified: 0, qualified: 0, readyForReview: 0 },
    budget: { used: 120, limit: 1500, unit: "نقطة" },
    stopReason: "WAITING_FOR_USER",
    waitingQuestion: {
      prompt: "كم عدد العملاء المحتملين الذين تريد مراجعتهم؟",
      options: ["3 عملاء", "5 عملاء", "10 عملاء"],
      kind: "choices",
    },
    timeline: [
      { at: minsAgo(40), event: "Job created", detail: "تم استلام الطلب من الشات" },
      { at: minsAgo(38), event: "Understanding intent", detail: "تحليل الهدف" },
      { at: minsAgo(36), event: "Waiting for user", detail: "النظام بحاجة لمعرفة عدد النتائج المطلوبة" },
    ],
    providerActivity: [],
    leadIds: [],
  },
  {
    id: "job_4",
    objective: "شركات تقنية مالية في الرياض تستخدم Salesforce.",
    icpVersion: 3,
    status: "PAUSED",
    createdById: "u_khalid",
    createdByName: "Khalid Al-Harbi",
    createdAt: hoursAgo(2),
    startedAt: hoursAgo(2),
    completedAt: null,
    stages: { discovered: 28, deduplicated: 22, researched: 0, verified: 0, qualified: 0, readyForReview: 0 },
    budget: { used: 340, limit: 1500, unit: "نقطة" },
    stopReason: "PROVIDER_UNAVAILABLE",
    pauseReason: "مزود البحث Exa وصل لحد الطلبات (429). يمكنك استئناف الوظيفة ليستخدم النظام Gemini Search كبديل في مرحلة البحث.",
    timeline: [
      { at: hoursAgo(2), event: "Job created", detail: "ICP v3" },
      { at: hoursAgo(1), event: "Discovery", detail: "28 مرشح" },
      { at: minsAgo(30), event: "Paused", detail: "Exa وصل لحد الطلبات" },
    ],
    providerActivity: [{ provider: "Exa", action: "آخر فشل — 429 rate limit", at: minsAgo(30) }],
    leadIds: [],
  },
  {
    id: "job_5",
    objective: "أرقام الجوالات الشخصية لمديري الشركات في الرياض.",
    icpVersion: 2,
    status: "FAILED",
    createdById: "u_noura",
    createdByName: "Noura Al-Otaibi",
    createdAt: daysAgo(5),
    startedAt: daysAgo(5),
    completedAt: daysAgo(5),
    stages: { discovered: 0, deduplicated: 0, researched: 0, verified: 0, qualified: 0, readyForReview: 0 },
    budget: { used: 40, limit: 1500, unit: "نقطة" },
    stopReason: "POLICY_BLOCK",
    failureDetail: "أوقفت سياسة المنصة هذا البحث: جمع بيانات التواصل الشخصية للأفراد غير مسموح. عدّل الهدف ليركّز على الشركات.",
    timeline: [
      { at: daysAgo(5), event: "Job created", detail: "ICP v2" },
      { at: daysAgo(5), event: "Policy block", detail: "الهدف يتعارض مع سياسة الاستخدام" },
    ],
    providerActivity: [],
    leadIds: [],
  },
];

export const providers = [
  { id: "p_exa", name: "Exa", capability: "Web Search / Discovery", status: "DEGRADED", health: "محدود", quota: 10000, usage: 8420, remaining: 1580, lastFailure: "429 rate limit — قبل 30 دقيقة", fallbackPosition: "المزود الأساسي للـDiscovery", rationale: "يُستخدم للـDiscovery لأنه يغطي الويب العميق. عند بلوغ الحد، يتحول النظام تلقائيًا إلى Gemini Search كـfallback." },
  { id: "p_gemini", name: "Gemini Search", capability: "Web Search / Grounded", status: "OPERATIONAL", health: "سليم", quota: 20000, usage: 6100, remaining: 13900, lastFailure: "—", fallbackPosition: "Fallback للـDiscovery", rationale: "يُستخدم كاحتياطي عند تعطل Exa، وكمصدر متقاطع للتحقق." },
  { id: "p_linkedin", name: "LinkedIn", capability: "People / Company Research", status: "OPERATIONAL", health: "سليم", quota: 5000, usage: 2210, remaining: 2790, lastFailure: "—", fallbackPosition: "أساسي لبيانات الأشخاص", rationale: "مصدر أساسي لعدد الموظفين وصانعي القرار. التحقق المتقاطع مع ZoomInfo." },
  { id: "p_zoominfo", capability: "Contact Data", name: "ZoomInfo", status: "OPERATIONAL", health: "سليم", quota: 3000, usage: 480, remaining: 2520, lastFailure: "—", fallbackPosition: "أساسي لبيانات الاتصال", rationale: "يُستخدم لكشف صانع القرار والتحقق من بيانات الاتصال." },
  { id: "p_google", name: "Google Maps", capability: "Location Verification", status: "OPERATIONAL", health: "سليم", quota: 15000, usage: 3200, remaining: 11800, lastFailure: "—", fallbackPosition: "أساسي للمواقع", rationale: "تحقق جغرافي عالي الموثوقية." },
];

export const credentials = [
  { id: "c_gemini", service: "Gemini", masked: "••••••••••92ab", connected: true, lastTested: minsAgo(12), status: "OK", note: "مفتاح API" },
  { id: "c_exa", service: "Exa", masked: "••••••••••1f84", connected: true, lastTested: hoursAgo(1), status: "OK", note: "مفتاح API" },
  { id: "c_linkedin", service: "LinkedIn", masked: "••••••••••c7a2", connected: true, lastTested: hoursAgo(3), status: "OK", note: "OAuth" },
  { id: "c_google", service: "Google Maps", masked: "••••••••••5d10", connected: true, lastTested: hoursAgo(5), status: "OK", note: "مفتاح API" },
  { id: "c_zoominfo", service: "ZoomInfo", masked: "— غير مُدخل —", connected: false, lastTested: null, status: "MISSING", note: "مطلوب لبيانات الاتصال" },
];

export const integrations = [
  { id: "i_google", name: "Google Workspace", category: "الإنتاجية", state: "connected", note: "مرتبط بحساب المؤسسة" },
  { id: "i_gmail", name: "Gmail", category: "البريد", state: "connected", note: "للإشعارات الداخلية فقط" },
  { id: "i_hubspot", name: "HubSpot", category: "CRM", state: "available", note: "تصدير العملاء المعتمدين لاحقًا" },
  { id: "i_slack", name: "Slack", category: "الإشعارات", state: "available", note: "تنبيهات الفريق" },
  { id: "i_linkedin", name: "LinkedIn", category: "المراسلة", state: "coming_later", note: "غير مدعوم بعد — النظام لا يراسل أي جهة" },
  { id: "i_whatsapp", name: "WhatsApp", category: "المراسلة", state: "coming_later", note: "غير مدعوم بعد" },
];

export const agents = [
  {
    id: "a_research", name: "Research Orchestrator", version: "v6.2", status: "ACTIVE",
    model: "gemini-2.5-pro",
    tools: [
      { name: "web_search", capability: "بحث ويب", permitted: true },
      { name: "company_research", capability: "بحث شركات", permitted: true },
      { name: "people_research", capability: "بحث أشخاص", permitted: true },
      { name: "verify_fact", capability: "تحقق", permitted: true },
      { name: "qualify_lead", capability: "تأهيل", permitted: true },
      { name: "approve_contact", capability: "اعتماد جهة اتصال", permitted: false },
      { name: "send_outbound", capability: "إرسال رسائل", permitted: false },
    ],
    recentRuns: 128, failures: 2, approvals: 0,
    note: "ينفّذ البحث من الاكتشاف حتى التأهيل. لا يملك صلاحية الاعتماد — هذا القرار للإنسان.",
  },
  {
    id: "a_verifier", name: "Fact Verifier", version: "v2.0", status: "ACTIVE",
    model: "gemini-2.5-flash",
    tools: [
      { name: "cross_check", capability: "تحقق متقاطع", permitted: true },
      { name: "freshness_check", capability: "فحص الحداثة", permitted: true },
      { name: "conflict_detect", capability: "كشف التعارض", permitted: true },
    ],
    recentRuns: 340, failures: 0, approvals: 0,
    note: "يحدّد حالة كل معلومة: متحقق، متعارض، قديم، أو استنتاجي.",
  },
];

export const activity = [
  { id: "ev_1", actor: "Noura Al-Otaibi", action: "اعتمدت جهة اتصال", target: "Thiqa Cloud (lead_4)", at: daysAgo(1), detail: "قرار: اعتماد جهة الاتصال" },
  { id: "ev_2", actor: "Noura Al-Otaibi", action: "رفضت Lead", target: "Bayan Analytics (lead_5)", at: daysAgo(3), detail: "خارج النطاق الجغرافي" },
  { id: "ev_3", actor: "Noura Al-Otaibi", action: "أنشأت ICP", target: "ICP v3", at: daysAgo(5), detail: "حصر الموقع في الرياض وإضافة فريق المبيعات" },
  { id: "ev_4", actor: "Noura Al-Otaibi", action: "أنشأت وظيفة بحث", target: "job_1", at: hoursAgo(6), detail: "ICP v3 — SaaS الرياض" },
  { id: "ev_5", actor: "SYSTEM", action: "بدّل المزود", target: "Exa ← Gemini Search", at: minsAgo(30), detail: "Exa بلغ حد الطلبات" },
  { id: "ev_6", actor: "Khalid Al-Harbi", action: "كشف بيانات الاتصال", target: "Nusuk Tech (lead_1)", at: minsAgo(8), detail: "السبب: مراجعة جهة الاتصال — مسجّل في سجل التدقيق" },
  { id: "ev_7", actor: "SYSTEM", action: "تحقق من حقيقة", target: "Nusuk Tech — عدد الموظفين", at: hoursAgo(2), detail: "الحالة: متعارض (LinkedIn 84 مقابل Bloomberg 120)" },
  { id: "ev_8", actor: "SYSTEM", action: "أوقف وظيفة", target: "job_4", at: minsAgo(30), detail: "متوقفة مؤقتًا — Exa وصل لحد الطلبات" },
];

export const notifications = [
  { id: "n_1", type: "review", title: "3 عملاء جاهزون للمراجعة", detail: "SaaS في الرياض", at: minsAgo(18), read: false, severity: "info", to: "/review" },
  { id: "n_2", type: "question", title: "وظيفة بحث تنتظر إجابتك", detail: "برمجيات مؤسسية في الرياض", at: minsAgo(36), read: false, severity: "warning", to: "/jobs/job_3" },
  { id: "n_3", type: "provider", title: "مزود البحث Exa محدود", detail: "بلغ حد الطلبات — توقفت وظيفة job_4", at: minsAgo(30), read: false, severity: "warning", to: "/jobs/job_4" },
  { id: "n_4", type: "capacity", title: "تم تجديد حصة LinkedIn", detail: "المتاح الآن 2,790 طلبًا", at: hoursAgo(2), read: true, severity: "success", to: "/providers" },
  { id: "n_5", type: "policy", title: "أوقفت السياسة وظيفة بحث", detail: "جمع بيانات شخصية غير مسموح", at: daysAgo(5), read: true, severity: "danger", to: "/jobs/job_5" },
];

export const currentUser = {
  id: "u_noura",
  name: "Noura Al-Otaibi",
  email: "noura@leadengine.ai",
  role: "admin",
  organization: "Lead Engine HQ",
};

// sample messages for the chat demo on first load
export const seedChat = [
  { id: "m_0", role: "user", text: "ابحث لي عن شركات SaaS في الرياض من 20 إلى 200 موظف، ويكون عندها فريق مبيعات.", at: hoursAgo(6) },
  { id: "m_1", role: "agent", text: "فهمت طلبك. سأبحث عن شركات SaaS في الرياض بحجم 20–200 موظف وتمتلك فريق مبيعات. هل تريد فقط الشركات التي لديها موقع رسمي؟", at: hoursAgo(6), status: "Understanding request" },
  { id: "m_2", role: "user", text: "نعم، موقع رسمي ضروري.", at: hoursAgo(6) },
  { id: "m_3", role: "agent", text: "ثبّتُّ ICP v3 الحالي لهذا البحث وبدأت الوظيفة job_1. سأعرض لك تقدّم المراحل هنا مباشرة.", at: hoursAgo(6), status: "Defining ICP" },
];

// templates for generated leads during chat-driven research
export const candidateCompanies = [
  { name: "Wusul Cloud", domain: "wusul.cloud", location: "الرياض", size: 67, sizeRange: "50–200", website: "https://wusul.cloud", founded: 2018, businessModel: "B2B", hasSalesTeam: true, industry: "SaaS", description: "منصة SaaS لإدارة التوصيل." },
  { name: "Marsos AI", domain: "marsos.ai", location: "الرياض", size: 41, sizeRange: "20–50", website: "https://marsos.ai", founded: 2020, businessModel: "B2B", hasSalesTeam: true, industry: "SaaS", description: "مساعد ذكي لفرق المبيعات." },
  { name: "Daleel CRM", domain: "daleel.sa", location: "الرياض", size: 120, sizeRange: "50–200", website: "https://daleel.sa", founded: 2017, businessModel: "B2B", hasSalesTeam: true, industry: "SaaS", description: "CRM مخصّص للسوق السعودي." },
  { name: "Nexah Tech", domain: "nexah.tech", location: "الرياض", size: 88, sizeRange: "50–200", website: "https://nexah.tech", founded: 2019, businessModel: "B2B", hasSalesTeam: null, industry: "SaaS", description: "أتمتة سير العمل للمؤسسات." },
  { name: "Rawabet Systems", domain: "rawabet.sa", location: "الرياض", size: 150, sizeRange: "50–200", website: "https://rawabet.sa", founded: 2015, businessModel: "B2B", hasSalesTeam: true, industry: "برمجيات مؤسسية", description: "أنظمة ERP للشركات المتوسطة." },
  { name: "Tahaluf Digital", domain: "tahaluf.digital", location: "الدمام", size: 74, sizeRange: "50–200", website: "https://tahaluf.digital", founded: 2018, businessModel: "B2B", hasSalesTeam: true, industry: "SaaS", description: "منصة إدارة العقود الرقمية." },
  { name: "Ofoq Labs", domain: "ofoq.io", location: "الرياض", size: 18, sizeRange: "10–20", website: "https://ofoq.io", founded: 2022, businessModel: "B2B", hasSalesTeam: false, industry: "SaaS", description: "أدوات تحليل لفرق المنتج." },
  { name: "Mizan Pay", domain: "mizanpay.sa", location: "الرياض", size: 95, sizeRange: "50–200", website: "https://mizanpay.sa", founded: 2019, businessModel: "B2B2C", hasSalesTeam: true, industry: "Fintech SaaS", description: "بوابة دفع للمتاجر الصغيرة." },
  { name: "Sanad Soft", domain: "sanadsoft.com", location: "الرياض", size: 62, sizeRange: "50–200", website: "https://sanadsoft.com", founded: 2016, businessModel: "B2B", hasSalesTeam: true, industry: "SaaS", description: "منصة خدمة عملاء متعددة القنوات." },
  { name: "Bawaba Tech", domain: "bawaba.tech", location: "الرياض", size: 230, sizeRange: "200+", website: "https://bawaba.tech", founded: 2013, businessModel: "B2B", hasSalesTeam: true, industry: "SaaS", description: "بوابات خدمة ذاتية للمؤسسات الكبيرة." },
];
