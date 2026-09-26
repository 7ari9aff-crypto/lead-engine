"""Company identity resolution (pure decisions).

Discovery output is NOT automatically truth: a raw result becomes a Company
only through identity resolution on stable identifiers (domain first, then
normalized name).
"""
from __future__ import annotations

from urllib.parse import urlparse

SOCIAL_DOMAINS = ("facebook.com", "instagram.com", "linkedin.com", "twitter.com",
                  "x.com", "tiktok.com", "youtube.com", "wa.me", "whatsapp.com")
EDITORIAL_HINTS = ("blog", "article", "news", "magazine", "/blog/", "best-", "top-10")


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
    return " ".join(name.lower().split())


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
    if looks_editorial(candidate_name, candidate_url):
        return "editorial"
    if known_by_domain or known_by_name:
        return "existing"
    return "new"
