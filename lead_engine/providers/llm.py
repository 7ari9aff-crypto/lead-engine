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

    def request(self, task, payload):
        # multi-turn agent path (chat): contents + optional function-calling tools
        if "contents" in payload:
            text, fcs, rate_info = self._generate(
                payload["contents"],
                system=payload.get("system_instruction"),
                tools=payload.get("tools"))
            return {"provider": self.name, "model": self.model_name, "text": text,
                    "function_calls": fcs, "rate_info": rate_info, "units": 1}
        return super().request(task, payload)

    def complete(self, prompt, json_mode):
        text, _fcs, rate_info = self._generate(
            [{"role": "user", "parts": [{"text": prompt}]}], json_mode=json_mode)
        return text, rate_info

    def _generate(self, contents, system=None, tools=None, json_mode=False):
        gen_cfg = {"temperature": 0.4}
        if json_mode:
            gen_cfg["responseMimeType"] = "application/json"
        body = {"contents": contents, "generationConfig": gen_cfg}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if tools:
            body["tools"] = tools
        resp = self._http(
            "POST", self.URL.format(model=self.model_name or "gemini-3.6-flash")
            + f"?key={self.current_key()}",
            json=body,
        )
        data = self._json(resp)
        parts = ((data.get("candidates") or [{}])[0].get("content", {}) or {}).get("parts", []) or []
        text = "".join(p.get("text", "") for p in parts if "text" in p)
        # keep the RAW functionCall parts (incl. thoughtSignature, required by
        # gemini-3.x when echoing the model turn back) alongside parsed view
        fcs = []
        for p in parts:
            if "functionCall" in p:
                fcs.append({"name": p["functionCall"]["name"],
                            "args": p["functionCall"].get("args") or {},
                            "_raw": p})
        return text, fcs, self._rate_info(resp.headers)


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
        return {"Authorization": f"Bearer {self.current_key()}"}


class OpenRouterProvider(_OpenAICompat):
    name = "openrouter"
    tasks = ("reasoning", "inference")
    env_key = "OPENROUTER_API_KEY"
    URL = "https://openrouter.ai/api/v1/chat/completions"

    def _headers(self):
        return {"Authorization": f"Bearer {self.current_key()}"}


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
