"""Multi-stage dedup.

Stage 1 — exact: normalized_domain / exact_email / exact_phone / linkedin
Stage 2 — company identity: normalized name + country + city
Stage 3 — fuzzy: name similarity within the same city+country.
  similarity > 0.95          -> auto merge (never when domains conflict)
  0.85 - 0.95                -> review pair (flagged, never auto-deleted)
  < 0.85                     -> separate
"""
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from .normalize import normalize_phone, normalize_text


@dataclass
class DedupStats:
    input_count: int = 0
    output_count: int = 0
    merged_count: int = 0
    duplicate_rate: float = 0.0
    review_pairs: list = field(default_factory=list)


def classify_ratio(ratio: float, auto: float, review: float) -> str:
    if ratio > auto:
        return "merge"
    if ratio >= review:
        return "review"
    return "separate"


class DedupEngine:
    def __init__(self, settings: dict):
        cfg = settings.get("dedup", {}) or {}
        self.auto = cfg.get("auto_merge_threshold", 0.95)
        self.review = cfg.get("review_threshold", 0.85)

    def run(self, leads: list):
        n = len(leads)
        stats = DedupStats(input_count=n)
        if n == 0:
            return [], stats
        parent = list(range(n))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(i, j):
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[max(ri, rj)] = min(ri, rj)

        # ---- Stage 1: exact identifiers
        keymap = {}
        for i, lead in enumerate(leads):
            keys = []
            if lead.get("domain"):
                keys.append("d:" + str(lead["domain"]).lower())
            if lead.get("email"):
                keys.append("e:" + str(lead["email"]).lower())
            if lead.get("phone"):
                keys.append("p:" + normalize_phone(lead["phone"]))
            if lead.get("linkedin"):
                keys.append("l:" + str(lead["linkedin"]).lower())
            if lead.get("source_id"):
                keys.append("s:" + str(lead["source_id"]))
            for key in keys:
                if key in keymap:
                    union(i, keymap[key])
                else:
                    keymap[key] = i

        # ---- Stage 2: company identity (name + country + city)
        # conflicting domains guard here too: same name in one city can still
        # be two different clinics — never merge on name alone.
        idmap = {}
        for i, lead in enumerate(leads):
            nm = normalize_text(lead.get("name"))
            if not nm:
                continue
            key = (nm, normalize_text(lead.get("country")), normalize_text(lead.get("city")))
            if key in idmap:
                j = idmap[key]
                di, dj = leads[i].get("domain"), leads[j].get("domain")
                if not (di and dj and str(di).lower() != str(dj).lower()):
                    union(i, j)
            else:
                idmap[key] = i

        # ---- Stage 3: fuzzy within same city+country
        by_city = {}
        for i, lead in enumerate(leads):
            by_city.setdefault(
                (normalize_text(lead.get("city")), normalize_text(lead.get("country"))), []
            ).append(i)
        review_flags = set()
        for _city, idxs in by_city.items():
            for a in range(len(idxs)):
                for b in range(a + 1, len(idxs)):
                    i, j = idxs[a], idxs[b]
                    if find(i) == find(j):
                        continue
                    di, dj = leads[i].get("domain"), leads[j].get("domain")
                    if di and dj and str(di).lower() != str(dj).lower():
                        continue  # conflicting domains -> never auto merge
                    ratio = SequenceMatcher(
                        None, normalize_text(leads[i].get("name")),
                        normalize_text(leads[j].get("name")),
                    ).ratio()
                    verdict = classify_ratio(ratio, self.auto, self.review)
                    if verdict == "merge":
                        union(i, j)
                    elif verdict == "review":
                        review_flags.add((min(i, j), max(i, j)))
                        stats.review_pairs.append(
                            {"a": leads[i].get("name"), "b": leads[j].get("name"),
                             "similarity": round(ratio, 3)}
                        )

        # ---- group and merge
        groups = {}
        for i in range(n):
            groups.setdefault(find(i), []).append(i)

        merged = []
        root_to_index = {}
        for root, idxs in groups.items():
            record = self._merge_group([leads[i] for i in idxs])
            if len(idxs) > 1:
                stats.merged_count += len(idxs) - 1
            root_to_index[root] = len(merged)
            merged.append(record)

        for pair in review_flags:
            for i in pair:
                merged[root_to_index[find(i)]]["requires_review"] = True

        stats.output_count = len(merged)
        stats.duplicate_rate = round((n - len(merged)) / n, 3) if n else 0.0
        return merged, stats

    @staticmethod
    def _merge_group(members: list) -> dict:
        out = {}
        for key in ("name", "domain", "website", "email", "phone", "city", "country",
                    "industry", "decision_maker", "decision_maker_title", "linkedin"):
            for m in members:
                if m.get(key):
                    out[key] = m[key]
                    break
        out["branches"] = max([m.get("branches") or 0 for m in members] + [0]) or None
        for key in ("sources", "source_queries", "source_urls"):
            seen = []
            for m in members:
                for item in m.get(key) or []:
                    if item not in seen:
                        seen.append(item)
            out[key] = seen
        socials = [m.get("social") for m in members if m.get("social")]
        if socials:
            out["social"] = "; ".join(dict.fromkeys(socials))
        for m in members:
            if m.get("snippet"):
                out["snippet"] = m["snippet"]
                break
        out["merged_count"] = len(members)
        out["source_ids"] = [m.get("lead_id") or m.get("source_id") for m in members]
        return out
