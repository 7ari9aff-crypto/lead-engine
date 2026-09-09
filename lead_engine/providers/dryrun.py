"""Offline dry-run adapters backed by fixtures/ — same router, zero network.

The router logic (priority, cache, quota) runs identically; only the HTTP
calls are replaced by deterministic fixture responses. This is how the V0
pipeline is tested end-to-end before any API key is spent.
"""
import json
import re

from ..config import FIXTURES_DIR


def _load(name):
    with open(FIXTURES_DIR / name, encoding="utf-8") as fh:
        return json.load(fh)


class DryRunSearch:
    tasks = ("web_search",)
    env_key = None
    available = True

    def __init__(self, settings, name="tavily"):
        self.name = name
        self.fixtures = _load("search_results.json")

    def request(self, task, payload):
        query = payload["query"].lower()
        tokens = [t for t in re.findall(r"[\w\u0600-\u06FF]+", query) if len(t) > 2]
        best, best_score = None, 0
        for fq, results in self.fixtures["queries"].items():
            fl = fq.lower()
            score = sum(1 for t in tokens if t in fl)
            if score > best_score:
                best, best_score = results, score
        results = best or self.fixtures.get("generic", [])
        return {"provider": self.name,
                "results": results[: payload.get("max_results", 8)], "units": 1}


class DryRunLLM:
    tasks = ("reasoning", "inference")
    env_key = None
    available = True

    def __init__(self, settings, name="gemini"):
        self.name = name

    def request(self, task, payload):
        lead = payload.get("lead") or {}
        blob = " ".join(str(lead.get(k) or "") for k in
                        ("name", "snippet", "industry", "decision_maker_title"))
        branches = 0
        m = re.search(r"(\d+)\s*(branches|branch|فرع|فروع)", blob)
        if m:
            branches = int(m.group(1))
        score = 40 + min(branches, 12) * 4
        if re.search(r"marketing|campaign|تسويق|إعلان|حملة", blob, re.IGNORECASE):
            score += 12
        if lead.get("decision_maker"):
            score += 6
        score = min(score, 95)
        tier = "A" if score >= 75 else ("B" if score >= 55 else "C")
        text = json.dumps({
            "score": score, "tier": tier,
            "reasons": ["dry-run deterministic mock"],
            "branches_estimated": branches or None,
            "marketing_signal": bool(re.search(r"marketing|campaign|تسويق|حملة", blob, re.I)),
        })
        return {"provider": self.name, "model": "dry-run-mock", "text": text, "units": 1}


class DryRunApollo:
    name = "apollo"
    tasks = ("people_search", "org_search", "enrichment")
    env_key = None
    available = True

    def __init__(self, settings):
        self.contacts = _load("apollo_contacts.json")

    def request(self, task, payload):
        if task == "people_search":
            people = []
            for domain in payload.get("domains") or []:
                c = self.contacts.get(domain)
                if c and c.get("decision_maker"):
                    # search does NOT return emails (0 credits, by design)
                    people.append({"name": c["decision_maker"], "title": c.get("title") or "",
                                   "organization": domain, "linkedin_url": c.get("linkedin_url") or "",
                                   "apollo_id": domain})
            return {"provider": self.name, "people": people, "units": 0}
        if task == "enrichment":
            contact = self.contacts.get(payload.get("domain") or "", {})
            if contact.get("email"):
                return {"provider": self.name,
                        "person": {"name": contact.get("decision_maker") or "",
                                   "title": contact.get("title") or "",
                                   "email": contact["email"], "phone": contact.get("phone"),
                                   "linkedin_url": contact.get("linkedin_url") or ""},
                        "units": 2}
            return {"provider": self.name, "person": {"email": None}, "units": 0}
        return {"provider": self.name, "organizations": [], "units": 0}


class DryRunEmailVerifier:
    tasks = ("email_verify", "email_find")
    env_key = None
    available = True

    def __init__(self, settings, name="hunter"):
        self.name = name
        self.rules = _load("email_domains.json")

    def request(self, task, payload):
        if task == "email_find":
            return {"provider": self.name, "emails": [], "units": 0}
        email = str(payload["email"]).lower()
        domain = email.rpartition("@")[2]
        status, confidence = self.rules.get(domain, ["DELIVERABLE", 0.6])
        return {"provider": self.name, "status": status, "confidence": confidence,
                "details": {"reason": "dry-run fixture"}, "units": 1}


class DryRunLocalSMTP:
    tasks = ("email_verify",)
    env_key = None
    available = True

    def __init__(self, settings):
        self.name = "local_smtp"

    def request(self, task, payload):
        return {"provider": self.name, "status": "UNKNOWN", "confidence": 0.1,
                "details": {"reason": "dry-run"}, "units": 0}


def build_dry_run_adapters(settings: dict) -> dict:
    search = DryRunSearch(settings, "tavily")
    llm = DryRunLLM(settings, "gemini")
    llm_local = DryRunLLM(settings, "ollama")
    apollo = DryRunApollo(settings)
    email = DryRunEmailVerifier(settings, "hunter")
    return {
        "tavily": search, "brave": DryRunSearch(settings, "brave"), "exa": DryRunSearch(settings, "exa"),
        "gemini": llm, "groq": DryRunLLM(settings, "groq"),
        "openrouter": DryRunLLM(settings, "openrouter"), "ollama": llm_local,
        "apollo": apollo,
        "hunter": email, "abstract": DryRunEmailVerifier(settings, "abstract"),
        "local_smtp": DryRunLocalSMTP(settings),
    }
