"""LLM pool: Gemini -> Groq -> OpenRouter Free -> Ollama local.

Groq/OpenRouter return rate-limit headers; they are parsed and pushed into
the registry so the router pauses a provider BEFORE the next 429.
"""
from .base import BaseProvider


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


class LLMBase(BaseProvider):
    ptype = "llm"

    def request(self, task, payload):
        prompt = payload["prompt"]
        json_mode = payload.get("json_mode", True)
        text, rate_info = self.complete(prompt, json_mode)
        return {"provider": self.name, "model": self.model_name, "text": text,
                "rate_info": rate_info, "units": 1}

    def complete(self, prompt, json_mode):
        raise NotImplementedError

    @property
    def model_name(self):
        return (self.settings.get("llm", {}).get("cloud_models", {}) or {}).get(self.name, "")


class GeminiProvider(LLMBase):
    name = "gemini"
    tasks = ("reasoning", "inference")
    env_key = "GEMINI_API_KEY"
    URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def complete(self, prompt, json_mode):
        model = self.model_name or "gemini-2.0-flash"
        gen_cfg = {"temperature": 0.2}
        if json_mode:
            gen_cfg["responseMimeType"] = "application/json"
        resp = self._http(
            "POST", self.URL.format(model=model) + f"?key={self.api_key}",
            json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": gen_cfg},
        )
        data = self._json(resp)
        parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
        return "".join(p.get("text", "") for p in parts), self._rate_info(resp.headers)


class _OpenAICompat(LLMBase):
    URL = ""

    def complete(self, prompt, json_mode):
        body = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        resp = self._http("POST", self.URL, json=body, headers=self._headers())
        data = self._json(resp)
        text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        return text, self._rate_info(resp.headers)


class GroqProvider(_OpenAICompat):
    name = "groq"
    tasks = ("reasoning", "inference")
    env_key = "GROQ_API_KEY"
    URL = "https://api.groq.com/openai/v1/chat/completions"

    def _headers(self):
        return {"Authorization": f"Bearer {self.api_key}"}


class OpenRouterProvider(_OpenAICompat):
    name = "openrouter"
    tasks = ("reasoning", "inference")
    env_key = "OPENROUTER_API_KEY"
    URL = "https://openrouter.ai/api/v1/chat/completions"

    def _headers(self):
        return {"Authorization": f"Bearer {self.api_key}"}


class OllamaProvider(LLMBase):
    """The real fallback. Unlimited locally, but flagged degraded."""
    name = "ollama"
    tasks = ("reasoning", "inference")
    env_key = None

    @property
    def model_name(self):
        return (self.settings.get("llm", {}) or {}).get("local_model", "llama3.1:8b")

    def complete(self, prompt, json_mode):
        base = (self.settings.get("llm", {}) or {}).get(
            "ollama_base_url", __import__("os").environ.get("OLLAMA_BASE_URL", "http://localhost:11434"))
        body = {"model": self.model_name, "messages": [{"role": "user", "content": prompt}],
                "stream": False}
        if json_mode:
            body["format"] = "json"
        resp = self._http("POST", f"{base.rstrip('/')}/api/chat", json=body)
        data = self._json(resp)
        return (data.get("message") or {}).get("content", ""), self._rate_info(resp.headers)
