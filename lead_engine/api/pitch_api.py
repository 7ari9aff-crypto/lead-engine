"""AI-powered outreach and pitch generation API.
Generates high-converting, personalized cold outreach assets (Email & WhatsApp)
tailored to the lead's domain, location, decision maker, and business focus.
Uses the engine Router (Gemini -> Groq -> fallback) to ensure 100% resilience.
"""
import json
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from ..config import load_settings, load_cache_policy
from ..cache import CacheLayer
from ..router import Router
router = APIRouter(tags=["pitch"])

def get_db(request: Request = None):
    """Delegated to the shared tenant module — one org resolution path
    (claims -> fail-closed, env bridge for token-less contexts)."""
    from ..tenant import db_handle

    yield from db_handle(request)

class PitchRequest(BaseModel):
    lead_id: str | None = None
    name: str
    city: str | None = None
    domain: str | None = None
    website: str | None = None
    decision_maker: str | None = None
    snippet: str | None = None
    industry: str | None = "b2b"
    offer: str | None = None

class PitchResponse(BaseModel):
    cold_email_subject: str
    cold_email_body: str
    whatsapp_message: str
    hook: str
    pain_points: list[str]

def _build_prompt(req: PitchRequest) -> str:
    offer_text = req.offer or "حلول زيادة المبيعات واكتساب عملاء جدد مؤهلين وأتمتة التواصل بالذكاء الاصطناعي"
    return f"""أنت خبير تسويق واستقطاب مبيعات B2B محترف ومستشار نمو أعمال دولي.
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
"""

def _generate_fallback(req: PitchRequest) -> dict:
    city_str = f" في {req.city}" if req.city else ""
    return {
        "cold_email_subject": f"استفسار سريع بخصوص نمو {req.name}{city_str}",
        "cold_email_body": f"أهلاً وسهلاً {req.decision_maker or 'المدير التنفيذي / المسؤول'}،\n\n"
                           f"لفت انتباهي تميز وتطور {req.name}{city_str} والخدمات الاحترافية التي تقدمونها.\n\n"
                           f"نساعد المنشآت الرائدة على زيادة تدفق العملاء المؤهلين وتسريع دورة المبيعات عبر حلول أتمتة ذكية متطورة.\n\n"
                           f"هل يناسبك مكالمة استكشافية سريعة لمدة 10 دقائق الأسبوع القادم لمشاركة تفاصيل التجربة؟\n\nمع خالص التقدير،",
        "whatsapp_message": f"السلام عليكم {req.decision_maker or 'أستاذنا الفاضل'}، أتمنى لك يوماً موفقاً 🌹\n\n"
                            f"متابع لتميز {req.name}{city_str}.. حبيت أستفسر لو متاح وقت قصير لمشاركة آلية عمل ساعدت شركات مماثلة على مضاعفة العملاء المحتملين بكفاءة؟",
        "hook": f"فرصة نوعية لتعزيز نمو {req.name} وتوسيع قاعدة العملاء المؤهلين{city_str}.",
        "pain_points": [
            "الحاجة لتدفق مستمر ومنتظم من العملاء والفرص البيعية المؤهلة",
            "طول دورة المبيعات وصعوبة الوصول لصناع القرار مباشرة",
            "أهمية الاستجابة الفورية للاستفسارات وتحويلها لصفقات مؤكدة"
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
    from ..tenant import org_clause

    # Tenant-scoped read: a lead from another organization must 404, not pitch.
    clause, clause_params = org_clause(db)
    row = db.one(f"SELECT * FROM leads WHERE lead_id=?{clause}",
                 (lead_id, *clause_params))
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
        industry=row.get("industry") or "b2b"
    )
    return _run_ai_pitch(db, req)
