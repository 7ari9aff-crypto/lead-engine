"""ICP planning (pure): turns an ICP definition into a bounded query plan.

The plan feeds Discovery; max_search_queries bounds provider spend (§17).
"""
from __future__ import annotations

from typing import Any


def build_query_plan(icp: dict[str, Any]) -> dict[str, Any]:
    cities = icp.get("cities") or []
    keywords_en = icp.get("keywords_en") or []
    keywords_ar = icp.get("keywords_ar") or []

    queries: list[dict[str, str]] = []
    for city in cities:
        name = city["name"] if isinstance(city, dict) else str(city)
        ar = (city.get("ar", name) if isinstance(city, dict) else name)
        for kw in keywords_en:
            queries.append({"q": f"{kw} in {name}", "city": name, "lang": "en"})
        for kw in keywords_ar:
            queries.append({"q": f"{kw} {ar}", "city": name, "lang": "ar"})

    limits = icp.get("v0_limits") or {}
    max_queries = limits.get("max_search_queries")
    if max_queries:
        queries = queries[: int(max_queries)]

    return {
        "icp": icp,
        "queries": queries,
        "results_per_query": int(limits.get("search_results_per_query", 6)),
    }


def is_empty_plan(plan: dict[str, Any]) -> bool:
    """An ICP with no cities/keywords yields zero queries — the caller must
    fail loudly instead of 'COMPLETED with nothing' (legacy bug, V6 rule)."""
    return not plan["queries"]
