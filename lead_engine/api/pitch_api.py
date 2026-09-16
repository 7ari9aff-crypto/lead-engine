"""AI-powered outreach and pitch generation API.

Generates high-converting, personalized cold outreach assets (Email & WhatsApp)
tailored to the lead's domain, location, decision maker, and clinical/business focus.
Uses the engine Router (Gemini -> Groq -> fallback) to ensure 100% resilience.
"""
import json
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..config import load_settings, load_cache_policy
from ..cache import CacheLayer
from ..db import open_db
from ..router import Router

router = APIRouter(tags=["pitch"])


def get_db(request: Request = None):
    db = open_db()
    try:
        if request is not None:
            claims = getattr(request.state, "claims", None)
            if claims:
                from .. import auth_jwt
                resolved = auth_jwt.resolve_org_id(claims, db)
                if resolved:
                    db.org_id = resolved
        yield db
    finally:
        db.conn.close()


class PitchRequest(BaseModel):
    lead_id: str | None = None
    name: str
    city: str | None = None
    domain: str | None = None
    website: str | None = None
    decision_maker: str | None = None
    snippet: str | None = None
    industry: str | None = "dental"
    offer: str | None = None


class PitchResponse(BaseModel):
    cold_email_subject: str
    cold_email_body: str
    whatsapp_message: str
    hook: str
    pain_points: list[str]


def _build_prompt(req: PitchRequest) -> str:
    offer_text = req.offer or "حلول زيادة الإيرادات وجلب عملاء ومرضى جدد وأتمتة المواعيد بالذكاء الاصطناعي"
    return f"""أنت خبير تسويق واستقطاب مبيعات B2B محترف في السوق السعودي والخليجي.
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
"""


def _generate_fallback(req: PitchRequest) -> dict:
    city_str = f" في {req.city}" if req.city else ""
    return {
        "cold_email_subject": f"سؤال سريع بخصوص نمو {req.name}{city_str}",
        "cold_email_body": f"أهلاً وسهلاً {req.decision_maker or 'دكتور / مدير المركز'}،\n\n"
                           f"لفت انتباهي تميز {req.name}{city_str} في تقديم خدمات الرعاية والاهتمام بالمرضى.\n\n"
                           f"نساعد العيادات الرائدة على مضاعفة حجز المواعيد المؤكدة وخفض الإلغاءات بنسبة 35% عبر أتمتة ذكية متوافقة تماماً مع السوق السعودي.\n\n"
                           f"هل يناسبك مكالمة تعريفية سريعة لمدة 10 دقائق الأسبوع القادم لاستعراض آلية العمل؟\n\nمع خالص التقدير،",
        "whatsapp_message": f"السلام عليكم {req.decision_maker or 'يا دكتور'}، أسعد الله أوقاتك بكل خير 🌹\n\n"
                            f"أنا متابع لتميز {req.name}{city_str}.. حبيت أستفسر لو متاح عندكم وقت بسيط لنقاش فكرة ساعدت عيادات مماثلة على زيادة تأكيد المواعيد بذكاء وسهولة؟",
        "hook": f"فرصة مميزة لتعزيز حصة {req.name} ومضاعفة المواعيد المؤكدة{city_str}.",
        "pain_points": [
            "ارتفاع معدل إلغاء المواعيد أو عدم الحضور (No-shows)",
            "الحاجة لجلب مرضى وعملاء ذوي قيمة عالية لخدمات التجميل والزراعة",
            "صعوبة المتابعة الفورية للاستفسارات الواردة عبر واتساب وانستجرام"
        ]
    }


def _run_ai_pitch(db, req: PitchRequest) -> PitchResponse:
    settings = load_settings()
    cache = CacheLayer(db, load_cache_policy())
    router_inst = Router(db, cache, settings)
    
    prompt = _build_prompt(req)
    try:
        res, meta = router_inst.route("reasoning", {"prompt": prompt, "json_mode": True})
        text = res.get("text", "")
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text
            if text.endswith("```"):
                text = text[:-3]
        parsed = json.loads(text.strip())
        return PitchResponse(
            cold_email_subject=parsed.get("cold_email_subject") or f"استفسار لـ {req.name}",
            cold_email_body=parsed.get("cold_email_body") or "",
            whatsapp_message=parsed.get("whatsapp_message") or "",
            hook=parsed.get("hook") or "",
            pain_points=parsed.get("pain_points") or []
        )
    except Exception:
        fallback = _generate_fallback(req)
        return PitchResponse(**fallback)


@router.post("/api/v1/pitch/generate", response_model=PitchResponse)
def generate_pitch(req: PitchRequest, db=Depends(get_db)):
    return _run_ai_pitch(db, req)


@router.post("/api/v1/leads/{lead_id}/pitch", response_model=PitchResponse)
def generate_pitch_for_lead(lead_id: str, db=Depends(get_db)):
    row = db.one("SELECT * FROM leads WHERE lead_id=?", (lead_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Lead not found")
        
    req = PitchRequest(
        lead_id=row.get("lead_id"),
        name=row.get("name") or "المنشأة",
        city=row.get("city"),
        domain=row.get("domain"),
        website=row.get("website"),
        decision_maker=row.get("decision_maker"),
        snippet=row.get("snippet"),
        industry="dental"
    )
    return _run_ai_pitch(db, req)
