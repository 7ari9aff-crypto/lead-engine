"""Company identity resolution (pure decisions).

Discovery output is NOT automatically truth: a raw result becomes a Company
only through identity resolution on stable identifiers (domain first, then
normalized name).
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

SOCIAL_DOMAINS = ("facebook.com", "instagram.com", "linkedin.com", "twitter.com",
                  "x.com", "tiktok.com", "youtube.com", "wa.me", "whatsapp.com")
EDITORIAL_HINTS = ("blog", "article", "news", "magazine", "/blog/", "best-", "top-10")

# Aggregator / directory sites: they LIST businesses, they are not one. A
# result on one of these used to become a bogus company row named after the
# directory page — one per listed clinic, same domain across "companies".
DIRECTORY_DOMAINS = ("whatclinic.com", "healthgrades.com", "zocdoc.com",
                     "vitals.com", "ratemds.com", "bookimed.com", "doctors.com",
                     "dentistry.com", "yellowpages.com", "yell.com", "yelp.com",
                     "houzz.com", "tripadvisor.com", "booking.com", "b2bmap.com",
                     "kompass.com", "dnb.com")


def is_directory(domain: str | None) -> bool:
    if not domain:
        return False
    return any(domain == d or domain.endswith("." + d) for d in DIRECTORY_DOMAINS)


def domain_from_url(url: str) -> str | None:
    try:
        host = urlparse(url).netloc.lower()
        host = host.removeprefix("www.")
        return host or None
    except ValueError:
        return None


def is_social(domain: str | None) -> bool:
    if not domain:
        return False
    return any(domain == d or domain.endswith("." + d) for d in SOCIAL_DOMAINS)


def looks_editorial(title: str, url: str) -> bool:
    blob = f"{title} {url}".lower()
    return any(h in blob for h in EDITORIAL_HINTS)


def normalize_name(name: str) -> str:
    """Display-safe cleanup (case + whitespace). NOT used for matching: use
    name_key(), which also folds Arabic spelling variants."""
    return " ".join(name.lower().split())


# --- Arabic-aware matching key ------------------------------------------
_AR_FOLD = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",   # alef variants
    "ى": "ي", "ئ": "ي",                          # alef maksura / hamza-on-yeh
    "ة": "ه",                                    # ta marbuta
    "ؤ": "و",                                    # hamza-on-waw
    "گ": "ك", "ک": "ك", "ی": "ي",                # Persian/Urdu letter forms
})
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
# tashkeel (harakat), superscript alef, tatweel
_AR_MARKS_RE = re.compile("[\u064B-\u065F\u0670\u0640]")
# The Arabic block also holds punctuation (، ؛ ؟ and the Arabic percent/decimal
# marks); those separate words, they are not letters.
_NON_WORD_RE = re.compile(r"[^\w\u0600-\u06FF]+|[\u060C\u061B\u061F\u066A-\u066D\u06D4]+", re.UNICODE)
# Words that describe the TYPE of business, not which business it is. Dropped
# only when something distinctive remains, so "Dental Clinic" alone is kept.
_GENERIC_TOKENS = frozenset({
    "clinic", "clinics", "center", "centre", "centers", "centres", "dental",
    "dentist", "dentistry", "medical", "hospital", "group", "co", "company",
    "ltd", "llc", "the", "and", "of", "in", "care", "specialty", "specialized",
    "specialist", "polyclinic", "service", "services", "health", "healthcare",
    "department", "dept", "unit", "خدمات", "قسم", "وحده",
    # geography: WHERE a business is says nothing about WHICH business it is.
    # (A different city is handled separately, as a veto, by name_match_is_safe.)
    "saudi", "arabia", "ksa", "riyadh", "jeddah", "jedda", "dammam", "khobar",
    "mecca", "makkah", "medina", "madinah", "egypt", "cairo", "giza", "alexandria",
    "uae", "dubai", "abudhabi", "السعوديه", "رياض", "جده", "دمام", "خبر", "مكه",
    "مدينه", "مصر", "قاهره", "دبي",
    # marketing filler that appears in page titles, not in business names
    "best", "top", "leading", "trusted", "your", "for", "with", "near", "you",
    "all", "needs", "excellence", "premium", "quality", "افضل", "اشهر", "دليل",
    "دليلك", "شامل", "الشامل", "لاختيار", "اختيار",
    "عياده", "عيادات", "مركز", "مراكز", "مجمع", "شركه", "مؤسسه", "مستشفي",
    "اسنان", "طب", "طبي", "في", "و",
})
# Honorifics are spelled many ways; fold them to one token so "د. سمير" and
# "دكتور سمير" (or "Dr." / "Doctor") match.
_TITLE_FORMS = {"د": "دكتور", "dr": "دكتور", "doctor": "دكتور", "دكتوره": "دكتور",
                "الدكتور": "دكتور", "الدكتوره": "دكتور", "prof": "بروفيسور",
                "professor": "بروفيسور", "أ": "", "ا": ""}
_PAREN_RE = re.compile(r"[\(\[][^\)\]]*[\)\]]")
# Arabic definite article, optionally fused with the preposition ل / و / ب / ك:
# الزهراء, للاسنان (ل+الاسنان), والزهراء, بالرياض -> bare stem
_AR_ARTICLE_RE = re.compile(r"^(?:[لوبك]?ال|لل)(?=\w{3,})")


def name_key(name: str | None) -> str:
    """Stable matching key for a business name, language-aware.

    Collapses spelling variants that real Saudi/Egyptian sources mix freely
    (أ/إ/آ -> ا, ى -> ي, ة -> ه, tashkeel, tatweel, Arabic-Indic digits,
    punctuation, the ``ال`` prefix) and drops generic business-type words so
    "Al Zahra Dental Center (@alzahradental)" and "Al Zahra Dental Clinic"
    share a key. Returns "" when nothing distinctive is left; callers must
    treat "" as "do not match by name"."""
    if not name:
        return ""
    s = str(name).lower().translate(_DIGITS)
    s = _PAREN_RE.sub(" ", s)          # "(@handle)" / "(branch)" is not the name
    s = _AR_MARKS_RE.sub("", s).translate(_AR_FOLD)
    s = s.replace("@", " ")
    tokens = [_TITLE_FORMS.get(t, t) for t in _NON_WORD_RE.sub(" ", s).split() if t]
    # "al"/"el" as a separate latin article
    tokens = [t for t in tokens if t not in ("al", "el")]
    tokens = [_AR_ARTICLE_RE.sub("", t) for t in tokens]
    tokens = [("طب" if t == "لطب" else t) for t in tokens]
    distinctive = [t for t in tokens if t and t not in _GENERIC_TOKENS]
    # a bare number/year ("2025") or punctuation is not a business name
    if not any(ch.isalpha() for t in distinctive for ch in t):
        return ""
    if not distinctive:
        return ""
    return " ".join(sorted(set(distinctive)))


def resolve_identity(
    candidate_name: str,
    candidate_url: str,
    known_by_domain: bool,
    known_by_name: bool,
) -> str:
    """Identity decision for a discovery candidate.

    Returns one of: 'social' (not a business site), 'editorial' (skip),
    'existing' (merge into known company), 'new' (create company).
    """
    domain = domain_from_url(candidate_url)
    if is_social(domain):
        return "social"
    if is_directory(domain):
        return "editorial"
    if looks_editorial(candidate_name, candidate_url):
        return "editorial"
    if known_by_domain or known_by_name:
        return "existing"
    return "new"


_TITLE_SPLIT_RE = re.compile(r"\s+[-|–—»]\s+|\s*[|:،]\s+")


def _alnum(text: str) -> str:
    return re.sub(r"[^a-z0-9\u0600-\u06FF]", "", text.lower())


def business_name_from_title(title: str, domain: str | None) -> str:
    """Pick the business name out of a search-result title, or return it unchanged.

    Titles look like "<tagline> - <Brand>", "<Brand> | <tagline>" or just a
    page headline, so NO fixed position is right (the legacy clean_title always
    kept the first part and drops "... - اوكي كلينيك"). The domain is the one
    reliable witness: keep the segment that the domain's registrable label
    spells (okclinics.sa <- "اوكي كلينيك" via Latin/Arabic overlap is NOT
    attempted; only Latin containment is, because transliteration would be
    guessing). If no segment is confirmed by the domain, the title is returned
    UNCHANGED: a long honest title beats a confidently wrong name."""
    title = " ".join((title or "").split())
    if not title or not domain:
        return title
    parts = [p.strip() for p in _TITLE_SPLIT_RE.split(title) if p and p.strip()]
    if len(parts) < 2:
        return title
    label = _alnum(domain.lower().removeprefix("www.").split(".")[0])
    if len(label) < 4:                      # too short to be evidence
        return title
    if label in _GENERIC_TOKENS or name_key(label) == "":
        return title                        # "clinic.com" would match any title
    hits = []
    for part in parts:
        flat = _alnum(part)
        # the segment must be (almost) the brand, not a sentence that merely
        # mentions it: bounded length and the label covers most of it
        if len(flat) >= 4 and (label in flat or flat in label) and len(flat) <= len(label) + 12:
            hits.append(part)
    return hits[0] if len(hits) == 1 else title


def name_match_is_safe(candidate_domain: str | None, existing_domain: str | None,
                       candidate_city: str | None = None,
                       existing_city: str | None = None) -> bool:
    """May a NAME match be trusted as "same company"?

    A name is weak evidence, a domain is strong. Merging on name alone collapsed
    three different "best dental clinic in Riyadh" articles (three domains) and
    "Jeddah Dental Center" with "Dentistry in Jeddah". Rules:
      * both sides have a domain and they differ -> different businesses, NEVER merge
      * both sides have a city and they differ   -> different branches, NEVER merge
      * otherwise (missing data on either side)  -> name match is acceptable
    A wrong merge silently destroys a lead; a missed merge only costs a
    duplicate row that the identity pipeline can still reconcile by domain."""
    cd, ed = (candidate_domain or "").lower(), (existing_domain or "").lower()
    if cd and ed and cd != ed:
        return False
    cc, ec = (candidate_city or "").strip().lower(), (existing_city or "").strip().lower()
    if cc and ec and cc != ec:
        return False
    return True


_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"(?:(?:\+|00)966|0)[\s\-]?\d{2,3}(?:[\s\-]?\d{3,4}){2}|\+\d{1,3}[\s\-]?\d{2,4}(?:[\s\-]?\d{3,4}){1,2}")
_WILD_EMAILS = ("example.com", "domain.com", "email.com", "yourdomain", "sentry.io",
                "wixpress", "@2x", ".png", ".jpg", ".webp", ".svg")


def extract_contacts(text: str) -> dict:
    """Contact extraction from unstructured snippet/title text — the same
    signal the legacy pipeline used, now a pure domain function.

    Returns {"emails": [...], "phones": [...]} deduplicated and filtered
    against obvious placeholder/junk patterns."""
    emails: list[str] = []
    for raw in _EMAIL_RE.findall(text or ""):
        candidate = raw.lower().strip(".")
        if any(bad in candidate for bad in _WILD_EMAILS):
            continue
        if candidate not in emails:
            emails.append(candidate)
    phones: list[str] = []
    for raw in _PHONE_RE.findall(text or ""):
        digits = re.sub(r"[^+0-9]", "", raw)
        if len(re.sub(r"\D", "", digits)) >= 9 and digits not in phones:
            phones.append(digits)
    return {"emails": emails[:3], "phones": phones[:2]}
