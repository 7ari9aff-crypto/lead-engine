"""Hard filter + scoring."""
from .icp import city_terms, industry_terms
from .normalize import normalize_text


class HardFilter:
    def __init__(self, icp: dict):
        self.city_terms = city_terms(icp)
        self.industry_terms = industry_terms(icp)

    def apply(self, lead: dict):
        blob = normalize_text(" ".join(str(lead.get(k) or "") for k in
                                       ("name", "domain", "snippet", "website", "city", "social")))
        if not any(t in blob for t in self.industry_terms):
            return False, "industry_mismatch"
        if not any(t in blob for t in self.city_terms):
            return False, "city_mismatch"
        return True, "ok"


class Scorer:
    def __init__(self, settings: dict):
        self.weights = (settings.get("scoring", {}) or {}).get("weights", {})
        self.weights.setdefault("qualification", 0.5)
        self.weights.setdefault("evidence", 0.2)
        self.weights.setdefault("contact", 0.2)
        self.weights.setdefault("verification", 0.1)

    def score(self, lead: dict) -> float:
        qualification = (lead.get("qualification_score") or 0) / 100.0
        evidence = min(1.0, len(lead.get("source_urls") or []) / 3.0)
        if lead.get("email") and lead.get("phone"):
            contact = 1.0
        elif lead.get("email") or lead.get("phone"):
            contact = 0.6
        elif lead.get("decision_maker"):
            contact = 0.3
        else:
            contact = 0.0
        status = lead.get("email_status")
        verification = 1.0 if status == "DELIVERABLE" else (
            0.5 if status in ("RISKY", "CATCH_ALL") else 0.0)
        w = self.weights
        total = (w["qualification"] * qualification + w["evidence"] * evidence +
                 w["contact"] * contact + w["verification"] * verification)
        return round(total * 100, 1)
