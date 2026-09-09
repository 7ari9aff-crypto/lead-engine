"""ICP Planner: turns an ICP file into a concrete query plan."""
from .normalize import normalize_text


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
