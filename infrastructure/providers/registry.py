"""Config-driven provider and model registry (extends ADR-0009).

Owner direction: new search tools, enrichment tools and models must be addable
by CONFIGURATION, not by editing code. ``config/providers.yaml`` lists them;
this module turns each enabled entry whose API key exists into a gateway
adapter. With no file the legacy ``bootstrap`` behavior is unchanged.

Entry kinds
-----------
``builtin``       an adapter that already ships in ``real.py`` (tavily, exa,
                  apollo, hunter, hunter-verify, smtp-verify, gemini); the
                  entry can override its priority.
``rest_search``   any JSON-over-HTTP search API, described declaratively.
``openai_compat`` any OpenAI-compatible chat-completions model (GLM, Qwen,
                  DeepSeek, OpenRouter, a local server, ...).

Secrets never leave the environment: entries name an ``env_key``; values are
read at call time and are never stored in, or reported by, this module.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import httpx

from contracts.providers import Capability, FailureClass, ProviderResult, ProviderSpec

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "providers.yaml"
_TIMEOUT = httpx.Timeout(25.0)
_ROTATE_ON = (401, 403, 429)

KINDS = ("builtin", "rest_search", "openai_compat")
# ModelGateway routes by free-form capability names (see build_model_gateway:
# "reasoning", "planning"), distinct from the provider ``Capability`` enum.
MODEL_CAPABILITIES = ("reasoning", "planning", "classification", "extraction")


class RegistryConfigError(ValueError):
    """The registry file is malformed. Raised at load time so a typo fails
    loudly instead of silently dropping a tool."""


@dataclass
class RegistryReport:
    """What was wired. Contains ids and reasons only, never key values."""

    registered: list[str] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)


# --------------------------------------------------------------------- keys
class _Keys:
    """Ordered multi-key pool read from one env var (comma/newline separated).
    The env is read lazily so hydration that runs after import still works."""

    def __init__(self, env_name: str):
        self.env_name = env_name
        self._index = 0

    def _all(self) -> list[str]:
        raw = (os.environ.get(self.env_name) or "").replace("\n", ",")
        return [k.strip() for k in raw.split(",") if k.strip()]

    def __len__(self) -> int:
        return len(self._all())

    def current(self) -> str | None:
        keys = self._all()
        return keys[min(self._index, len(keys) - 1)] if keys else None

    def rotate(self) -> bool:
        if self._index < len(self._all()) - 1:
            self._index += 1
            return True
        return False


def _client(transport: httpx.BaseTransport | None) -> httpx.Client:
    return httpx.Client(timeout=_TIMEOUT, transport=transport)


# ------------------------------------------------------------ templating
def _fill(value: Any, params: dict[str, Any]) -> Any:
    """Substitute ``{name}`` placeholders. A value that is exactly one
    placeholder keeps the parameter's type (so ``{max_results}`` stays int)."""
    if isinstance(value, str):
        if value.startswith("{") and value.endswith("}") and value.count("{") == 1:
            return params.get(value[1:-1], "")
        out = value
        for k, v in params.items():
            out = out.replace("{" + k + "}", str(v))
        return out
    if isinstance(value, dict):
        return {k: _fill(v, params) for k, v in value.items()}
    if isinstance(value, list):
        return [_fill(v, params) for v in value]
    return value


def _dig(data: Any, path: str) -> Any:
    for part in [p for p in (path or "").split(".") if p]:
        if isinstance(data, dict):
            data = data.get(part)
        elif isinstance(data, list) and part.isdigit() and int(part) < len(data):
            data = data[int(part)]
        else:
            return None
    return data


def _classify_status(code: int) -> FailureClass:
    if code == 429:
        return FailureClass.RATE_LIMIT
    if code in (401, 403):
        return FailureClass.AUTH
    if code in (402, 503):
        return FailureClass.CAPACITY
    if code in (400, 404, 422):
        return FailureClass.VALIDATION
    return FailureClass.TRANSIENT if code >= 500 else FailureClass.PERMANENT


# ---------------------------------------------------------- generic adapters
class RestSearchAdapter:
    """A declarative JSON search API. See ``config/providers.yaml`` for the
    full shape; everything vendor-specific lives in ``settings``."""

    def __init__(self, entry: dict[str, Any], transport=None):
        s = entry.get("settings") or {}
        self._url = s["url"]
        self._method = str(s.get("method", "POST")).upper()
        self._auth = s.get("auth") or {"type": "bearer"}
        self._body = s.get("body") or {}
        self._results_path = s.get("results_path", "results")
        self._fields = {"title": "title", "url": "url", "snippet": "snippet",
                        **(s.get("fields") or {})}
        self._transport = transport
        self._keys = _Keys(entry["env_key"])
        self.spec = ProviderSpec(
            provider_id=entry["id"], capability=Capability(entry["capability"]),
            priority=int(entry["priority"]),
            cost_cents_per_call=int(entry.get("cost_cents_per_call", 0)))

    def _headers(self, key: str) -> dict[str, str]:
        kind = self._auth.get("type", "bearer")
        if kind == "bearer":
            return {"Authorization": f"Bearer {key}"}
        if kind == "header":
            return {self._auth.get("name", "X-Api-Key"): key}
        return {}

    def call(self, operation: str, params: dict[str, Any]) -> ProviderResult:
        if not len(self._keys):
            return ProviderResult(ok=False, failure=FailureClass.AUTH,
                                  error=f"{self._keys.env_name} not set")
        filled = _fill(self._body, params)
        while True:
            key = self._keys.current()
            query = {self._auth.get("name", "api_key"): key} \
                if self._auth.get("type") == "query" else None
            try:
                with _client(self._transport) as client:
                    if self._method == "GET":
                        resp = client.get(self._url, params={**(filled or {}), **(query or {})},
                                          headers=self._headers(key))
                    else:
                        resp = client.post(self._url, json=filled, params=query,
                                           headers=self._headers(key))
                    resp.raise_for_status()
                    data = resp.json()
            except httpx.HTTPStatusError as exc:
                code = exc.response.status_code
                if code in _ROTATE_ON and self._keys.rotate():
                    continue
                return ProviderResult(ok=False, failure=_classify_status(code),
                                      error=f"HTTP {code}")
            except httpx.HTTPError as exc:
                return ProviderResult(ok=False, failure=FailureClass.TRANSIENT,
                                      error=type(exc).__name__)
            rows = _dig(data, self._results_path) or []
            results = [{
                "title": str(_dig(r, self._fields["title"]) or ""),
                "url": str(_dig(r, self._fields["url"]) or ""),
                "snippet": str(_dig(r, self._fields["snippet"]) or "")[:400],
                "provider": self.spec.provider_id,
            } for r in rows if isinstance(r, dict)]
            return ProviderResult(ok=True, data={"results": results,
                                                 "provider": self.spec.provider_id},
                                  cost_cents=self.spec.cost_cents_per_call)


class OpenAICompatModel:
    """Any OpenAI-compatible ``/chat/completions`` endpoint."""

    def __init__(self, entry: dict[str, Any], transport=None):
        s = entry.get("settings") or {}
        self._base = str(s["base_url"]).rstrip("/")
        self.model_id = s["model"]
        self._extra = s.get("params") or {}
        self._transport = transport
        self._keys = _Keys(entry["env_key"])

    def complete(self, capability: str, prompt: str, params: dict[str, Any]) -> Any:
        from infrastructure.models.gateway import ModelReply

        if not len(self._keys):
            raise RuntimeError(f"{self._keys.env_name} missing")
        while True:
            try:
                with _client(self._transport) as client:
                    resp = client.post(
                        f"{self._base}/chat/completions",
                        headers={"Authorization": f"Bearer {self._keys.current()}"},
                        json={"model": self.model_id, **self._extra,
                              "messages": [{"role": "user", "content": prompt}]})
                    resp.raise_for_status()
                    data = resp.json()
                break
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in _ROTATE_ON and self._keys.rotate():
                    continue
                raise
        text = (_dig(data, "choices.0.message.content") or "")
        return ModelReply(text=text, model_id=self.model_id, cost_cents=0,
                          tokens=int((data.get("usage") or {}).get("total_tokens", 0)))


# ------------------------------------------------------------- builtin map
def _builtin_factories() -> dict[str, Any]:
    from infrastructure.providers import real

    return {
        "tavily": real.TavilySearchAdapter, "exa": real.ExaSearchAdapter,
        "apollo": real.ApolloContactAdapter, "hunter": real.HunterContactAdapter,
        "hunter-verify": real.HunterVerifyAdapter,
        "smtp-verify": real.SmtpVerifyAdapter, "gemini": real.GeminiReasonModel,
    }


# ----------------------------------------------------------------- loading
def load_registry_config(path: Path | str | None = None) -> dict[str, Any] | None:
    """Parse the YAML file; ``None`` when it does not exist (legacy behavior)."""
    import yaml

    p = Path(path) if path else DEFAULT_PATH
    if not p.exists():
        return None
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise RegistryConfigError(f"{p}: top level must be a mapping")
    return {"version": data.get("version", 1),
            "providers": data.get("providers") or [],
            "models": data.get("models") or []}


def _valid_capabilities(group: str) -> set[str]:
    return set(MODEL_CAPABILITIES) if group == "model" else {c.value for c in Capability}


def _validate(entry: dict[str, Any], group: str, seen: set[str]) -> None:
    if not entry.get("id"):
        raise RegistryConfigError(f"{group} entry missing 'id': {entry}")
    eid = entry["id"]
    if eid in seen:
        raise RegistryConfigError(f"duplicate id '{eid}'")
    seen.add(eid)
    if entry.get("kind") not in KINDS:
        raise RegistryConfigError(f"'{eid}': unknown kind '{entry.get('kind')}' "
                                  f"(allowed: {', '.join(KINDS)})")
    cap = entry.get("capability")
    valid = _valid_capabilities(group)
    if cap not in valid:
        raise RegistryConfigError(f"'{eid}': unknown capability '{cap}' "
                                  f"(allowed: {', '.join(sorted(valid))})")
    if "priority" not in entry:
        raise RegistryConfigError(f"'{eid}': missing 'priority'")
    if entry["kind"] != "builtin" and not entry.get("env_key"):
        raise RegistryConfigError(f"'{eid}': missing 'env_key'")
    if group == "model" and entry["kind"] == "rest_search":
        raise RegistryConfigError(f"'{eid}': rest_search is a tool kind, not allowed under models")
    if group == "provider" and entry["kind"] == "openai_compat":
        raise RegistryConfigError(f"'{eid}': openai_compat is a model kind, not allowed under providers")
    if entry["kind"] == "rest_search" and not (entry.get("settings") or {}).get("url"):
        raise RegistryConfigError(f"'{eid}': rest_search needs settings.url")
    if entry["kind"] == "openai_compat":
        s = entry.get("settings") or {}
        if not s.get("base_url") or not s.get("model"):
            raise RegistryConfigError(f"'{eid}': openai_compat needs settings.base_url and settings.model")


def build_from_config(config: dict[str, Any], *, gateway=None, model_gateway=None,
                      transport: httpx.BaseTransport | None = None) -> RegistryReport:
    """Register every enabled entry whose key is present. Validation of the
    whole file happens first so a bad entry never half-applies."""
    report = RegistryReport()
    seen: set[str] = set()
    entries = [(e, "provider") for e in config.get("providers", [])] + \
              [(e, "model") for e in config.get("models", [])]
    for entry, group in entries:
        _validate(entry, group, seen)

    for entry, group in entries:
        eid = entry["id"]
        if entry.get("enabled", True) is False:
            report.skipped[eid] = "disabled"
            continue
        env_key = entry.get("env_key")
        if env_key and not (os.environ.get(env_key) or "").strip():
            report.skipped[eid] = f"{env_key} not set"
            continue

        if entry["kind"] == "builtin":
            factory = _builtin_factories().get(entry.get("builtin", eid))
            if factory is None:
                raise RegistryConfigError(f"'{eid}': unknown builtin '{entry.get('builtin')}'")
            adapter = factory()
            if group == "model":
                if model_gateway is not None:
                    model_gateway.register(entry["capability"], adapter, int(entry["priority"]))
            elif gateway is not None:
                adapter.spec = replace(adapter.spec, priority=int(entry["priority"]))
                gateway.register(adapter)
        elif entry["kind"] == "rest_search":
            if gateway is not None:
                gateway.register(RestSearchAdapter(entry, transport))
        else:  # openai_compat
            if model_gateway is not None:
                model_gateway.register(entry["capability"],
                                       OpenAICompatModel(entry, transport),
                                       int(entry["priority"]))
        report.registered.append(eid)
    return report
