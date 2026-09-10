"""ICP Planner: turns an ICP file into a concrete query plan."""
from .normalize import normalize_text

CITY_ALIASES = {
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
}

# cities where the pipeline has actually been exercised — unknown cities work
# too (alias falls back to the raw name) but with lower extraction confidence.


def build_adhoc_icp(cities: list, industry: str = "dental",
                    max_queries: int = 6, max_results: int = 6) -> dict:
    """Turn a chat/MCP request like 'الرياض + dental' into a full ICP dict."""
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
    }


def build_plan(icp: dict) -> dict:
    queries = []
    for city in icp.get("cities", []):
        for kw in icp.get("keywords_en", []):
            queries.append({"q": f"{kw} in {city['name']}", "city": city["name"], "lang": "en"})
        for kw in icp.get("keywords_ar", []):
            queries.append({"q": f"{kw} {city['ar']}", "city": city["name"], "lang": "ar"})

    limits = icp.get("v0_limits", {}) or {}
    if limits.get("max_search_queries"):
        queries = queries[: int(limits["max_search_queries"])]

    return {
        "icp": icp,
        "queries": queries,
        "apollo_titles": (icp.get("criteria", {}) or {}).get("decision_maker_roles", []),
        "apollo_locations": [c["name"] for c in icp.get("cities", [])],
    }


def city_terms(icp: dict):
    """All name variants for the ICP cities, normalized for matching."""
    terms = []
    for city in icp.get("cities", []):
        terms.append(normalize_text(city["name"]))
        terms.append(normalize_text(city.get("ar", "")))
    return [t for t in terms if t]


def industry_terms(icp: dict):
    terms = [normalize_text(k) for k in icp.get("keywords_en", []) + icp.get("keywords_ar", [])]
    terms.append(normalize_text(icp.get("industry", "")))
    return [t for t in terms if t]
