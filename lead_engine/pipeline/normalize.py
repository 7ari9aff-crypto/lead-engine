"""Text/domain/phone normalization — shared by dedup, filters, discovery."""
import re
from urllib.parse import urlparse

AR_NORMALIZE = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا",
    "ى": "ي", "ة": "ه",
    "ؤ": "و", "ئ": "ي",
})
PUNCT_RE = re.compile(r"[^\w\u0600-\u06FF\s]+", re.UNICODE)
WS_RE = re.compile(r"\s+")

SOCIAL_DOMAINS = {
    "facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com",
    "tiktok.com", "youtube.com", "snapchat.com", "wa.me", "whatsapp.com",
    "google.com", "goo.gl", "maps.app.goo.gl", "reddit.com", "quora.com",
}


def normalize_text(s: str) -> str:
    if not s:
        return ""
    s = str(s).lower().translate(AR_NORMALIZE)
    s = PUNCT_RE.sub(" ", s)
    return WS_RE.sub(" ", s).strip()


def domain_from_url(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.lower()
    except ValueError:
        return ""
    netloc = netloc.split("@")[-1].split(":")[0]
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc


def is_social(domain: str) -> bool:
    if not domain:
        return False
    return any(domain == d or domain.endswith("." + d) for d in SOCIAL_DOMAINS)


def clean_title(title: str) -> str:
    """Drop directory-style suffixes: 'Clinic X | Best Dental' -> 'Clinic X'."""
    t = title or ""
    t = re.split(r"\s*[|–—»]\s*|\s+-\s+", t)[0]
    return t.strip()


def normalize_phone(phone: str, country: str = "") -> str:
    """Normalize a phone number to E.164 format.
    Supports any international phone number; country hint is optional."""
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        return ""
    # Already has country code (starts with international prefix digits)
    if phone.strip().startswith("+"):
        return "+" + digits
    # KSA local format hint
    if country == "SA":
        if digits.startswith("966"):
            return "+" + digits
        if digits.startswith("0") and len(digits) == 10:
            return "+966" + digits[1:]
    # Generic: strip leading zero (common local prefix in many countries)
    if digits.startswith("0") and len(digits) >= 8:
        digits = digits[1:]
    return "+" + digits


# ---------------------------------------------------------------- contacts
EMAIL_TEXT_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# International phone patterns — ordered from most specific to most generic.
# Matches: +CC, 00CC, or local formats with 7-15 digits (ITU-T E.164 range).
PHONE_PATTERNS = [
    # E.164 with leading +
    re.compile(r"\+[1-9]\d{6,14}"),
    # 00-prefixed international dialing (e.g. 00966...)
    re.compile(r"00[1-9]\d{6,13}"),
    # KSA specifics (kept for backwards-compat when country='SA')
    re.compile(r"(?:9200\d{5})"),                               # KSA unified 920x
    re.compile(r"(?:0[5-9]\d{8})"),                            # local mobile 0XXX (10 digits)
    # Generic local: 7–12 digits possibly with spaces/dashes
    re.compile(r"\b\d{2,4}[\s\-]?\d{3,4}[\s\-]?\d{3,5}\b"),
]


def extract_contacts(text: str, country: str = ""):
    """Pull phone numbers / emails straight from search snippets.
    Evidence-backed contacts (the snippet cites its source URL) — they make
    the pipeline useful before Apollo/Hunter keys are configured.
    Works internationally for any market."""
    text = text or ""
    phones = []
    for pat in PHONE_PATTERNS:
        for match in pat.findall(text):
            norm = normalize_phone(match, country)
            digits = re.sub(r"\D", "", norm)
            # Minimum 7 digits (local) to maximum 15 (E.164)
            if not (7 <= len(digits) <= 16):
                continue
            if norm not in phones:
                phones.append(norm)
    email_match = EMAIL_TEXT_RE.search(text)
    email = email_match.group(0).lower() if email_match else None
    return phones[:3], email
