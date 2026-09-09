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


def normalize_phone(phone: str, country: str = "SA") -> str:
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        return ""
    if country == "SA":
        if digits.startswith("966"):
            return "+" + digits
        if digits.startswith("0") and len(digits) == 10:
            return "+966" + digits[1:]
    return "+" + digits
