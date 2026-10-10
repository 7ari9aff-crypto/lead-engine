"""Purchase-intent detection (pure) — the ZoomInfo-style lite signal.

Discovery snippets and page titles are scanned for bilingual intent
markers (hiring, expansion, new branches, funding, active marketing).
Each hit becomes an intent_signal row; intent_count is exposed on
company_context so qualification can prioritize warm accounts.
Pure functions only — no I/O.
"""
from __future__ import annotations

import re

from .company import normalize_name

# (kind, bilingual markers). kind is the stored signal kind.
INTENT_MARKERS: list[tuple[str, tuple[str, ...]]] = [
    ("hiring", ("we are hiring", "we're hiring", "now hiring", "join our team",
                "careers", "وظائف", "نوظف", "انضم لفريق")),
    ("expansion", ("new branch", "opening soon", "expansion", "franchise",
                   "new clinic", "second location", "فرع جديد", "افتتاح",
                   "توسع", "فرعنا الجديد")),
    ("funding", ("raised", "funding", "seed round", "series a", "investment",
                 "تمويل", "جولة استثمارية")),
    ("marketing_active", ("book now", "book appointment", "احجز موعد",
                           "special offer", "discount", "عرض خاص", "خصم")),
]

_MARKERS_RE = [(kind, re.compile(
    "|".join(re.escape(m) for m in markers), re.IGNORECASE))
    for kind, markers in INTENT_MARKERS]


def detect_intent(text: str) -> list[tuple[str, str]]:
    """Return [(kind, matched_marker)] for each distinct intent kind found."""
    blob = normalize_name(text or "")
    if not blob:
        return []
    hits: list[tuple[str, str]] = []
    seen: set[str] = set()
    for kind, rx in _MARKERS_RE:
        m = rx.search(blob)
        if m and kind not in seen:
            hits.append((kind, m.group(0).lower()))
            seen.add(kind)
    return hits
