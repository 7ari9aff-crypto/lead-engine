import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

def update_file(path, replacements):
    full_path = os.path.join(r"d:\lead generation", path)
    with open(full_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    orig = content
    for old, new in replacements:
        if old not in content:
            print(f"[WARN] In {path}: Target string not found: {old[:50]}")
        content = content.replace(old, new)
    
    if content != orig:
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[OK] Updated {path}")
    else:
        print(f"[NOOP] No changes for {path}")

# 4. web/src/pages/Pricing.tsx
update_file("web/src/pages/Pricing.tsx", [
    (
        """  {
    q: "هل يدعم PDPL السعودي؟",
    a: "نعم. البوابة القانونية (Legal Gate) PDPL-aware. يحجب أي شركة بدون إجماع قانوني قبل ما توصل لسجلّك. default-deny.",
  },""",
        """  {
    q: "هل يتوافق النظام مع معايير حماية البيانات والخصوصية العالمية (GDPR / Privacy Laws)؟",
    a: "نعم تمامًا. البوابة القانونية والأمنية تفحص الشركات والبيانات المعلنة B2B وتستبعد أي بيانات غير متوافقة وفق مبدأ default-deny المشدد.",
  },"""
    )
])

# 5. web/src/pages/Landing.tsx
update_file("web/src/pages/Landing.tsx", [
    (
        """    desc: "كل مهمة بتدوّر فعليًا في السوق السعودي عبر مزوّدين حقيقيين بمفاتيحك — من أول البحث لحد العميل المؤهل، وكل خطوة موثقة بمصدرها.\",""",
        """    desc: "كل مهمة تبحث وتكتشف الشركات والعملاء المؤهلين عبر مزوّدين حقيقيين بمفاتيحك — من أول البحث حتى العميل المؤهل، وكل خطوة موثقة بمصدرها.\","""
    ),
    (
        """            شغّال فعليًا على السوق السعودي — بأرقام حقيقية""",
        """            محرك استقطاب عالمي دقيق — بأرقام ونتائج حقيقية"""
    ),
    (
        """              صنع في السعودية""",
        """              Lead Engine — Global B2B Lead Intelligence"""
    )
])

# 6. web/src/pages/Verify.tsx
update_file("web/src/pages/Verify.tsx", [
    (
        """placeholder="name@clinic.com\"""",
        """placeholder="name@company.com\""""
    )
])

# 7. web/src/pages/Config.tsx
update_file("web/src/pages/Config.tsx", [
    (
        """              placeholder="مثال: عيادة أسنان" />""",
        """              placeholder="مثال: برمجيات سحابية / SaaS" />"""
    ),
    (
        """              placeholder="مثال: dental clinic" />""",
        """              placeholder="مثال: b2b software" />"""
    )
])

# 8. web/src/lib/friendly.ts
update_file("web/src/lib/friendly.ts", [
    (
        """export const ICP_LABELS: Record<string, string> = {
  v0_saudi_dental: "عيادات الأسنان — السعودية",
};""",
        """export const ICP_LABELS: Record<string, string> = {
  v0_saudi_dental: "حملة استقطاب نموذجية (Demo)",
};"""
    )
])

# 9. lead_engine/api/pitch_api.py
update_file("lead_engine/api/pitch_api.py", [
    (
        """tailored to the lead's domain, location, decision maker, and clinical/business focus.""",
        """tailored to the lead's domain, location, decision maker, and business focus."""
    ),
    (
        """    industry: str | None = "dental\"""",
        """    industry: str | None = "b2b\""""
    ),
    (
        """def _build_prompt(req: PitchRequest) -> str:
    offer_text = req.offer or "حلول زيادة الإيرادات وجلب عملاء ومرضى جدد وأتمتة المواعيد بالذكاء الاصطناعي"
    return f\"\"\"أنت خبير تسويق واستقطاب مبيعات B2B محترف في السوق السعودي والخليجي.
قم بصياغة رسائل تواصل واستقطاب باردة وشديدة الإقناع والملاءمة للمنشأة التالية:

اسم المنشأة: {req.name}
المدينة: {req.city or "المملكة العربية السعودية"}
الموقع الإلكتروني: {req.domain or req.website or "غير محدد"}
صانع القرار المستهدف: {req.decision_maker or "المدير التنفيذي / مالك العيادة"}
مجال العمل: {req.industry or "عيادات أسنان"}
تفاصيل ونبذة: {req.snippet or "عيادة متخصصة تقدم خدمات طبية وتجميلية"}
عرض القيمة المقدم: {offer_text}

المطلوب: توليد رد بتنسيق JSON حصراً يحتوي على المفاتيح التالية:
1. "cold_email_subject": عنوان إيميل جذاب وقصير يثير الفضول بدون أن يبدو كإعلان عشوائي.
2. "cold_email_body": نص بريد إلكتروني بارد احترافي وموجز (أقل من 120 كلمة)، يبدأ بنقطة تخص المنشأة، ثم القيمة المضافة، ودعوة لاتصال قصير (CTA).
3. "whatsapp_message": رسالة واتساب افتتاحية سريعة، ودودة واحترافية باللهجة السعودية البيضاء أو فصحى مبسطة تناسب وتيرة الواتساب السريعة مع سؤال مفتوح.
4. "hook": جملة واحدة افتتاحية قوية مبنية على مجالهم ومدينتهم.
5. "pain_points": قائمة بـ 2 إلى 3 تحديات محتملة يواجهونها في مجالهم في هذه المدينة.

أخرج JSON فقط بدون أي مقدمات أو علامات إضافية خارج الـ JSON.
\"\"\"""",
        """def _build_prompt(req: PitchRequest) -> str:
    offer_text = req.offer or "حلول زيادة المبيعات واكتساب عملاء جدد مؤهلين وأتمتة التواصل بالذكاء الاصطناعي"
    return f\"\"\"أنت خبير تسويق واستقطاب مبيعات B2B محترف ومستشار نمو أعمال دولي.
قم بصياغة رسائل تواصل واستقطاب باردة وشديدة الإقناع والملاءمة للمنشأة التالية:

اسم المنشأة: {req.name}
المدينة/الموقع: {req.city or "عام"}
الموقع الإلكتروني: {req.domain or req.website or "غير محدد"}
صانع القرار المستهدف: {req.decision_maker or "المدير التنفيذي / المسؤول"}
مجال العمل: {req.industry or "شركات ومؤسسات B2B"}
تفاصيل ونبذة: {req.snippet or "منشأة متخصصة تقدم خدمات متميزة"}
عرض القيمة المقدم: {offer_text}

المطلوب: توليد رد بتنسيق JSON حصراً يحتوي على المفاتيح التالية:
1. "cold_email_subject": عنوان إيميل جذاب وقصير يثير الفضول بدون أن يبدو كإعلان ترويجي مزعج.
2. "cold_email_body": نص بريد إلكتروني بارد احترافي وموجز (أقل من 120 كلمة)، يبدأ بنقطة تقدير لنشاط المنشأة، ثم القيمة المضافة وعائد الاستثمار، ودعوة لاتصال تعريفي موجز (CTA).
3. "whatsapp_message": رسالة افتتاحية سريعة وموجزة ومهنية تناسب وتيرة المراسلات السريعة مع سؤال استكشافي ذكي.
4. "hook": جملة واحدة افتتاحية قوية مبنية على مجالهم وتطورهم.
5. "pain_points": قائمة بـ 2 إلى 3 تحديات رئيسية شائعة يواجهونها في مجالهم وكيفية التغلب عليها.

أخرج JSON فقط بدون أي مقدمات أو علامات إضافية خارج الـ JSON.
\"\"\""""
    ),
    (
        """def _generate_fallback(req: PitchRequest) -> dict:
    city_str = f" في {req.city}" if req.city else ""
    return {
        "cold_email_subject": f"سؤال سريع بخصوص نمو {req.name}{city_str}",
        "cold_email_body": f"أهلاً وسهلاً {req.decision_maker or 'دكتور / مدير المركز'}،\\n\\n"
                           f"لفت انتباهي تميز {req.name}{city_str} في تقديم خدمات الرعاية والاهتمام بالمرضى.\\n\\n"
                           f"نساعد العيادات الرائدة على مضاعفة حجز المواعيد المؤكدة وخفض الإلغاءات بنسبة 35% عبر أتمتة ذكية متوافقة تماماً مع السوق السعودي.\\n\\n"
                           f"هل يناسبك مكالمة تعريفية سريعة لمدة 10 دقائق الأسبوع القادم لاستعراض آلية العمل؟\\n\\nمع خالص التقدير،",
        "whatsapp_message": f"السلام عليكم {req.decision_maker or 'يا دكتور'}، أسعد الله أوقاتك بكل خير 🌹\\n\\n"
                            f"أنا متابع لتميز {req.name}{city_str}.. حبيت أستفسر لو متاح عندكم وقت بسيط لنقاش فكرة ساعدت عيادات مماثلة على زيادة تأكيد المواعيد بذكاء وسهولة؟",
        "hook": f"فرصة مميزة لتعزيز حصة {req.name} ومضاعفة المواعيد المؤكدة{city_str}.",
        "pain_points": [
            "ارتفاع معدل إلغاء المواعيد أو عدم الحضور (No-shows)",
            "الحاجة لجلب مرضى وعملاء ذوي قيمة عالية لخدمات التجميل والزراعة",
            "صعوبة المتابعة الفورية للاستفسارات الواردة عبر واتساب وانستجرام"
        ]
    }""",
        """def _generate_fallback(req: PitchRequest) -> dict:
    city_str = f" في {req.city}" if req.city else ""
    return {
        "cold_email_subject": f"استفسار سريع بخصوص نمو {req.name}{city_str}",
        "cold_email_body": f"أهلاً وسهلاً {req.decision_maker or 'المدير التنفيذي / المسؤول'}،\\n\\n"
                           f"لفت انتباهي تميز وتطور {req.name}{city_str} والخدمات الاحترافية التي تقدمونها.\\n\\n"
                           f"نساعد المنشآت الرائدة على زيادة تدفق العملاء المؤهلين وتسريع دورة المبيعات عبر حلول أتمتة ذكية متطورة.\\n\\n"
                           f"هل يناسبك مكالمة استكشافية سريعة لمدة 10 دقائق الأسبوع القادم لمشاركة تفاصيل التجربة؟\\n\\nمع خالص التقدير،",
        "whatsapp_message": f"السلام عليكم {req.decision_maker or 'أستاذنا الفاضل'}، أتمنى لك يوماً موفقاً 🌹\\n\\n"
                            f"متابع لتميز {req.name}{city_str}.. حبيت أستفسر لو متاح وقت قصير لمشاركة آلية عمل ساعدت شركات مماثلة على مضاعفة العملاء المحتملين بكفاءة؟",
        "hook": f"فرصة نوعية لتعزيز نمو {req.name} وتوسيع قاعدة العملاء المؤهلين{city_str}.",
        "pain_points": [
            "الحاجة لتدفق مستمر ومنتظم من العملاء والفرص البيعية المؤهلة",
            "طول دورة المبيعات وصعوبة الوصول لصناع القرار مباشرة",
            "أهمية الاستجابة الفورية للاستفسارات وتحويلها لصفقات مؤكدة"
        ]
    }"""
    ),
    (
        """        industry="dental\"""",
        """        industry=row.get("industry") or "b2b\""""
    )
])

# 10. lead_engine/pipeline/icp.py
update_file("lead_engine/pipeline/icp.py", [
    (
        """CITY_ALIASES = {
    "الرياض": ("Riyadh", "الرياض"), "riyadh": ("Riyadh", "الرياض"),
    "جدة": ("Jeddah", "جدة"), "jeddah": ("Jeddah", "جدة"),
    "الدمام": ("Dammam", "الدمام"), "dammam": ("Dammam", "الدمام"),
    "الخبر": ("Khobar", "الخبر"), "khobar": ("Khobar", "الخبر"),
    "مكة": ("Makkah", "مكه"), "مكه": ("Makkah", "مكه"), "makkah": ("Makkah", "مكه"),
    "المدينة": ("Madinah", "المدينه"), "medina": ("Madinah", "المدينه"),
    "أبها": ("Abha", "ابها"), "abha": ("Abha", "ابها"),
    "الطائف": ("Taif", "الطايف"), "taif": ("Taif", "الطايف"),
}

INDUSTRY_KEYWORDS = {
    "dental": (["dental clinic", "dentist"], ["عيادة أسنان", "عيادات أسنان", "طبيب أسنان"]),
}""",
        """CITY_ALIASES = {
    "دبي": ("Dubai", "دبي"), "dubai": ("Dubai", "دبي"),
    "القاهرة": ("Cairo", "القاهرة"), "cairo": ("Cairo", "القاهرة"),
    "لندن": ("London", "لندن"), "london": ("London", "لندن"),
    "نيويورك": ("New York", "نيويورك"), "new york": ("New York", "نيويورك"),
    "إسطنبول": ("Istanbul", "إسطنبول"), "istanbul": ("Istanbul", "إسطنبول"),
    "الرياض": ("Riyadh", "الرياض"), "riyadh": ("Riyadh", "الرياض"),
    "جدة": ("Jeddah", "جدة"), "jeddah": ("Jeddah", "جدة"),
    "الدوحة": ("Doha", "الدوحة"), "doha": ("Doha", "الدوحة"),
    "المنامة": ("Manama", "المنامة"), "manama": ("Manama", "المنامة"),
    "الكويت": ("Kuwait City", "الكويت"), "kuwait": ("Kuwait City", "الكويت"),
}

INDUSTRY_KEYWORDS = {
    "dental": (["dental clinic", "dentist"], ["عيادة أسنان", "عيادات أسنان", "طبيب أسنان"]),
    "saas": (["b2b software", "saas company"], ["شركة برمجيات", "حلول سحابية"]),
    "marketing": (["marketing agency", "digital advertising"], ["وكالة تسويق", "تسويق رقمي"]),
    "realestate": (["real estate company", "property development"], ["شركة عقارات", "تطوير عقاري"]),
    "logistics": (["logistics company", "freight forwarding"], ["شركة خدمات لوجستية", "شحن"]),
    "b2b": (["b2b services", "consulting firm"], ["خدمات أعمال", "استشارات"]),
}"""
    ),
    (
        """def build_adhoc_icp(cities: list, industry: str = "dental",
                    max_queries: int = 6, max_results: int = 6) -> dict:
    \"\"\"Turn a chat/MCP request like 'الرياض + dental' into a full ICP dict.\"\"\"
    resolved = []
    for city in cities:
        key = str(city).strip().lower()
        name, ar = CITY_ALIASES.get(key, (str(city).strip(), str(city).strip()))
        if (name, ar) not in resolved:
            resolved.append((name, ar))
    kw_en, kw_ar = INDUSTRY_KEYWORDS.get(industry, ([industry], [industry]))
    names = [n for n, _ in resolved]
    return {
        "icp_id": f"adhoc_{industry}_{'_'.join(names)[:40]}",
        "name": f"Ad-hoc {industry} — {', '.join(names)}",
        "country": "SA",
        "legal_policy": "sa",
        "cities": [{"name": n, "ar": a} for n, a in resolved],
        "industry": industry,
        "keywords_en": kw_en,
        "keywords_ar": kw_ar,
        "criteria": {
            "min_branches": 0,
            "marketing_signals": [],
            "decision_maker_roles": ["owner", "practice manager", "مالك", "مدير"],
        },
        "v0_limits": {
            "search_results_per_query": max_results,
            "max_search_queries": max_queries,
            "enrichment_budget_credits": 0,
            "enrichment_max_people": 0,
        },
    }""",
        """def build_adhoc_icp(cities: list, industry: str = "b2b",
                    max_queries: int = 6, max_results: int = 6) -> dict:
    \"\"\"Turn a chat/MCP request into a full dynamic ICP dict.\"\"\"
    resolved = []
    for city in cities:
        key = str(city).strip().lower()
        name, ar = CITY_ALIASES.get(key, (str(city).strip(), str(city).strip()))
        if (name, ar) not in resolved:
            resolved.append((name, ar))
    kw_en, kw_ar = INDUSTRY_KEYWORDS.get(industry, ([f"{industry} company", industry], [f"شركة {industry}", industry]))
    names = [n for n, _ in resolved] if resolved else ["Global"]
    return {
        "icp_id": f"adhoc_{industry}_{'_'.join(names)[:40]}",
        "name": f"Ad-hoc {industry} — {', '.join(names)}",
        "country": "GLOBAL",
        "legal_policy": "standard",
        "cities": [{"name": n, "ar": a} for n, a in resolved],
        "industry": industry,
        "keywords_en": kw_en,
        "keywords_ar": kw_ar,
        "criteria": {
            "min_branches": 0,
            "marketing_signals": [],
            "decision_maker_roles": ["CEO", "Founder", "Owner", "Managing Director", "مدير", "مالك", "الرئيس التنفيذي"],
        },
        "v0_limits": {
            "search_results_per_query": max_results,
            "max_search_queries": max_queries,
            "enrichment_budget_credits": 0,
            "enrichment_max_people": 0,
        },
    }"""
    )
])

# 11. lead_engine/api/chat.py
update_file("lead_engine/api/chat.py", [
    (
        """"description": "المدينة السعودية مثل: الرياض، جدة، الدمام\"""",
        """"description": "المدينة أو المنطقة المستهدفة (مثال: دبي، الرياض، لندن، القاهرة، سنغافورة...)\""""
    ),
    (
        """"description": "المجال — الافتراضي dental (عيادات أسنان)",
                                 "enum": ["dental"]""",
        """"description": "المجال أو القطاع المستهدف (مثال: saas, b2b, realestate, logistics, dental, marketing...)\""""
    ),
    (
        """args.get("industry", "dental")""",
        """args.get("industry", "b2b")"""
    ),
    (
        """دور على شركات SaaS في السعودية بين 100 و500 موظف""",
        """دور على شركات برمجيات B2B توظف 50 إلى 200 موظف ولديها نشاط نمو"""
    )
])

# 12. lead_engine/api/mcp.py
update_file("lead_engine/api/mcp.py", [
    (
        """"industry": {"type": "string", "enum": ["dental"], "description": "افتراضي dental"},""",
        """"industry": {"type": "string", "description": "القطاع المستهدف (افتراضي b2b)"},"""
    )
])

print("All delocalization replacements executed successfully.")
