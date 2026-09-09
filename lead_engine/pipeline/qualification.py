"""AI qualification through the LLM pool.

Per design, basic qualification is allowed on the local model when the
cloud pool is exhausted — the lead is then flagged degraded_local so it
can be queued for manual review.
"""
import json

from ..router import NoProviderAvailable

PROMPT = """You are a strict B2B lead qualification analyst.
Score the lead 0-100 against the ICP. Consider: branch count, marketing
activity, decision-maker access, location fit, evidence quality.
Return ONLY strict JSON, no prose:
{{"score": <0-100>, "tier": "A"|"B"|"C", "reasons": ["..."],
  "branches_estimated": <int or null>, "marketing_signal": <bool>}}

ICP JSON:
{icp}

Lead JSON:
{lead}
"""


def _strip_fences(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


class Qualifier:
    def __init__(self, router):
        self.router = router

    def qualify(self, lead: dict, icp: dict, job_id=None) -> dict:
        payload = {
            "prompt": PROMPT.format(
                icp=json.dumps(icp, ensure_ascii=False, default=str),
                lead=json.dumps(lead, ensure_ascii=False, default=str),
            ),
            "json_mode": True,
            "lead": lead,
        }
        try:
            result, meta = self.router.route("reasoning", payload, job_id=job_id)
        except NoProviderAvailable as exc:
            return {"skipped": True, "reason": str(exc)}
        try:
            data = json.loads(_strip_fences(result.get("text", "")))
            score = float(data["score"])
            assert 0 <= score <= 100
        except (json.JSONDecodeError, KeyError, ValueError, AssertionError, TypeError):
            return {"score": None, "tier": None, "requires_review": True,
                    "reason": "llm_output_unparseable", "provider": meta.get("provider")}
        mode = "degraded_local" if meta.get("provider") == "ollama" else "cloud"
        return {
            "score": score,
            "tier": data.get("tier"),
            "reasons": data.get("reasons", []),
            "branches_estimated": data.get("branches_estimated"),
            "marketing_signal": bool(data.get("marketing_signal")),
            "processing_mode": mode,
            "provider": meta.get("provider"),
        }
