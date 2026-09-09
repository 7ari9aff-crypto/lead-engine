"""Selective enrichment: Apollo people search (0 credits) for decision
makers, enrichment (1-9 credits/person) only within a hard budget for
top-scored candidates."""
from ..router import NoProviderAvailable


class Enrichment:
    def __init__(self, router):
        self.router = router

    def run(self, leads: list, plan: dict, job_id=None) -> dict:
        icp = plan["icp"]
        limits = (icp.get("v0_limits", {}) or {})
        budget = float(limits.get("enrichment_budget_credits", 50))
        max_people = int(limits.get("enrichment_max_people", 30))
        stats = {"attempted": 0, "enriched": 0, "credits_used": 0.0, "skipped_budget": 0}

        for lead in leads:
            if stats["credits_used"] >= budget or stats["attempted"] >= max_people:
                stats["skipped_budget"] = max(0, len(leads) - stats["attempted"])
                break
            if not lead.get("domain"):
                continue
            stats["attempted"] += 1
            locations = [lead.get("city")] if lead.get("city") else plan["apollo_locations"]
            try:
                result, _meta = self.router.route(
                    "people_search",
                    {"titles": plan["apollo_titles"], "locations": locations,
                     "domains": [lead["domain"]]},
                    job_id=job_id,
                    cache_data_type="apollo_people_search",
                )
            except NoProviderAvailable:
                continue
            people = result.get("people") or []
            if not people:
                continue
            top = people[0]
            if top.get("name"):
                lead["decision_maker"] = top["name"]
            if top.get("title"):
                lead["decision_maker_title"] = top["title"]
            if top.get("linkedin_url"):
                lead["linkedin"] = top["linkedin_url"]

            if not lead.get("email"):
                try:
                    eres, _emeta = self.router.route(
                        "enrichment",
                        {"name": top.get("name", ""), "domain": lead["domain"]},
                        job_id=job_id,
                        cache_data_type="apollo_enrichment",
                    )
                except NoProviderAvailable:
                    continue
                units = float(eres.get("units", 0))
                stats["credits_used"] += units
                person = eres.get("person") or {}
                if person.get("email"):
                    lead["email"] = person["email"]
                    stats["enriched"] += 1
                if person.get("phone"):
                    lead["phone"] = person["phone"]
        return stats
