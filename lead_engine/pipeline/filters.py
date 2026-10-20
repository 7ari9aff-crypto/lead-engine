"""Hard filter + scoring."""
from .icp import city_terms, industry_terms
from .normalize import normalize_text


class HardFilter:
    def __init__(self, icp: dict):
        self.city_terms = city_terms(icp)
        self.industry_terms = industry_terms(icp)
        # criteria.min_branches is a real ICP criterion; it was defined in the
        # ICP config but never read here. Enforced only when the branch count
        # is KNOWN — an unknown value passes (we cannot filter on missing data).
        self.min_branches = int((icp.get("criteria") or {}).get("min_branches") or 0)

    def apply(self, lead: dict):
        blob = normalize_text(" ".join(str(lead.get(k) or "") for k in
                                       ("name", "domain", "snippet", "website", "city", "social")))
        if not any(t in blob for t in self.industry_terms):
            return False, "industry_mismatch"
        if not any(t in blob for t in self.city_terms):
            return False, "city_mismatch"
        branches = lead.get("branches")
        if self.min_branches and branches is not None and int(branches) < self.min_branches:
            return False, "branches_below_minimum"
        return True, "ok"


class Scorer:
    def __init__(self, settings: dict):
        # Copy: never mutate the shared settings dict (setdefault on the
        # original polluted it for every other consumer).
        weights = dict((settings.get("scoring", {}) or {}).get("weights", {}) or {})
        for key, default in (("qualification", 0.5), ("evidence", 0.2),
                             ("contact", 0.2), ("verification", 0.1)):
            weights.setdefault(key, default)
        # A partially customised set (e.g. only qualification=0.9) used to sum
        # to 1.4 and push scores past 100. Normalise so the total is 1.0.
        total = sum(v for v in weights.values() if v > 0) or 1.0
        self.weights = {k: max(v, 0) / total for k, v in weights.items()}

    def score(self, lead: dict) -> float:
        qualification = (lead.get("qualification_score") or 0) / 100.0
        evidence = min(1.0, len(lead.get("source_urls") or []) / 3.0)
        # An email the verifier proved INVALID is not a way to reach anyone, so
        # it must not count as contact data (it used to add up to +12 points).
        has_email = bool(lead.get("email")) and lead.get("email_status") != "INVALID"
        if has_email and lead.get("phone"):
            contact = 1.0
        elif has_email or lead.get("phone"):
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
