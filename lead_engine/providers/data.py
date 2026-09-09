"""Apollo — candidate discovery / selective enrichment.

People search and org search do not consume credits; enrichment costs
1-9 credits per person. The pipeline therefore: discovers -> hard filters
-> enriches only the top candidates within a credit budget.
"""
from .base import BaseProvider


class ApolloProvider(BaseProvider):
    name = "apollo"
    ptype = "data"
    tasks = ("people_search", "org_search", "enrichment")
    env_key = "APOLLO_API_KEY"
    BASE = "https://api.apollo.io/v1"

    def request(self, task, payload):
        return getattr(self, task)(payload)

    def _post(self, path, body):
        body = dict(body)
        body["api_key"] = self.api_key
        return self._json(self._http("POST", self.BASE + path, json=body,
                                     headers={"Content-Type": "application/json"}))

    def people_search(self, payload):
        data = self._post("/mixed_people/search", {
            "person_titles": payload.get("titles", []),
            "person_locations": payload.get("locations", []),
            "organization_domains": payload.get("domains", []),
            "page": payload.get("page", 1),
        })
        people = [
            {"name": p.get("name", ""), "title": p.get("title", ""),
             "organization": (p.get("organization") or {}).get("name", ""),
             "linkedin_url": p.get("linkedin_url", ""), "apollo_id": p.get("id", "")}
            for p in data.get("people", [])
        ]
        return {"provider": self.name, "people": people, "units": 0}

    def org_search(self, payload):
        data = self._post("/mixed_companies/search", {
            "q_organization_keyword_tags": payload.get("keywords", []),
            "organization_locations": payload.get("locations", []),
            "page": payload.get("page", 1),
        })
        orgs = [
            {"name": o.get("name", ""), "domain": o.get("primary_domain", ""),
             "employees": o.get("estimated_num_employees"), "locations": o.get("locations", [])}
            for o in data.get("organizations", data.get("accounts", []))
        ]
        return {"provider": self.name, "organizations": orgs, "units": 1}

    def enrichment(self, payload):
        # costs 1-9 credits depending on returned data — budgeted upstream
        data = self._post("/people/match", {
            "name": payload.get("name", ""), "domain": payload.get("domain", ""),
            "reveal_personal_emails": False,
        })
        person = data.get("person") or {}
        email = person.get("email")
        units = 1 if email else 0
        return {"provider": self.name,
                "person": {"name": person.get("name", ""), "title": person.get("title", ""),
                           "email": email, "phone": person.get("phone"),
                           "linkedin_url": person.get("linkedin_url", "")},
                "units": units}
