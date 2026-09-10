"""Discovery: ICP queries -> search pool -> raw candidates."""
from .icp import build_plan  # re-export for convenience
from .normalize import clean_title, domain_from_url, extract_contacts, is_social


class Discovery:
    def __init__(self, router):
        self.router = router

    def run(self, plan: dict, job_id=None) -> list:
        icp = plan["icp"]
        max_results = (icp.get("v0_limits", {}) or {}).get("search_results_per_query", 8)
        candidates = []
        for entry in plan["queries"]:
            result, meta = self.router.route(
                "web_search",
                {"query": entry["q"], "max_results": max_results},
                job_id=job_id,
                cache_data_type="search_results",
            )
            for r in result.get("results", []):
                candidates.append(self.to_candidate(r, entry, icp, meta.get("provider")))
        return candidates

    @staticmethod
    def to_candidate(result: dict, entry: dict, icp: dict, provider: str) -> dict:
        domain = domain_from_url(result.get("url", ""))
        social = is_social(domain)
        phones, email = extract_contacts(
            f"{result.get('title', '')} {result.get('snippet', '')}",
            icp.get("country") or "SA")
        return {
            "name": clean_title(result.get("title", "")),
            "domain": None if social else domain,
            "website": None if social else result.get("url"),
            "social": result.get("url") if social else None,
            "snippet": result.get("snippet", ""),
            "city": entry["city"],
            "country": icp.get("country"),
            "industry": icp.get("industry"),
            "phone": phones[0] if phones else None,
            "email": email,
            "contact_source": "snippet" if (phones or email) else None,
            "sources": ["search_api"],
            "source_queries": [entry["q"]],
            "source_urls": [result.get("url")],
            "source_provider": provider,
        }
