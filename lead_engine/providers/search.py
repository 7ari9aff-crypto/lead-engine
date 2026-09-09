"""Search pool: Tavily -> Brave -> Exa (priority from the registry)."""
from .base import BaseProvider

SOCIAL_EXCLUDE = ["facebook.com", "instagram.com", "linkedin.com", "twitter.com",
                  "x.com", "tiktok.com", "youtube.com", "google.com", "maps.google"]


class TavilyProvider(BaseProvider):
    name = "tavily"
    ptype = "search"
    tasks = ("web_search",)
    env_key = "TAVILY_API_KEY"
    URL = "https://api.tavily.com/search"

    def request(self, task, payload):
        depth = payload.get("depth", "basic")
        body = {
            "api_key": self.api_key,
            "query": payload["query"],
            "search_depth": depth,
            "max_results": payload.get("max_results", 8),
            "exclude_domains": payload.get("exclude_domains", SOCIAL_EXCLUDE),
        }
        data = self._json(self._http("POST", self.URL, json=body))
        results = [
            {"title": r.get("title", ""), "url": r.get("url", ""),
             "snippet": r.get("content", "")}
            for r in data.get("results", [])
        ]
        return {"provider": self.name, "results": results, "units": 2 if depth == "advanced" else 1}


class BraveProvider(BaseProvider):
    name = "brave"
    ptype = "search"
    tasks = ("web_search",)
    env_key = "BRAVE_SEARCH_API_KEY"
    URL = "https://api.search.brave.com/res/v1/web/search"

    def request(self, task, payload):
        data = self._json(self._http(
            "GET", self.URL,
            params={"q": payload["query"], "count": payload.get("max_results", 8)},
            headers={"X-Subscription-Token": self.api_key, "Accept": "application/json"},
        ))
        results = [
            {"title": r.get("title", ""), "url": r.get("url", ""),
             "snippet": r.get("description", "")}
            for r in (data.get("web") or {}).get("results", [])
        ]
        return {"provider": self.name, "results": results, "units": 1}


class ExaProvider(BaseProvider):
    name = "exa"
    ptype = "search"
    tasks = ("web_search",)
    env_key = "EXA_API_KEY"
    URL = "https://api.exa.ai/search"

    def request(self, task, payload):
        data = self._json(self._http(
            "POST", self.URL,
            json={"query": payload["query"], "numResults": payload.get("max_results", 8),
                  "type": "auto", "contents": {"text": {"maxCharacters": 400}}},
            headers={"x-api-key": self.api_key},
        ))
        results = [
            {"title": r.get("title", ""), "url": r.get("url", ""),
             "snippet": (r.get("text") or "")[:400]}
            for r in data.get("results", [])
        ]
        return {"provider": self.name, "results": results, "units": 1}
