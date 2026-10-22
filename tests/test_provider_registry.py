"""Config-driven provider/model registry.

The contract (owner direction, Oct 2026): adding a search tool or a model must
be a CONFIG change, not a code change. The built-in vendors keep working
exactly as before when no config file exists.
"""
from __future__ import annotations

import httpx
import pytest

from contracts.providers import Capability
from infrastructure.providers.gateway import ProviderGateway
from infrastructure.providers.registry import (
    RegistryConfigError,
    build_from_config,
    load_registry_config,
)


def _cfg(*entries):
    return {"version": 1, "providers": list(entries), "models": []}


REST_SEARCH = {
    "id": "acme-search",
    "kind": "rest_search",
    "capability": "search_companies",
    "priority": 15,
    "enabled": True,
    "env_key": "ACME_API_KEY",
    "settings": {
        "url": "https://api.acme.test/search",
        "method": "POST",
        "auth": {"type": "bearer"},
        "body": {"q": "{query}", "limit": "{max_results}"},
        "results_path": "hits",
        "fields": {"title": "name", "url": "link", "snippet": "text"},
    },
}


def test_rest_search_is_added_by_config_only(monkeypatch):
    monkeypatch.setenv("ACME_API_KEY", "k1")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={"hits": [
            {"name": "Alpha", "link": "https://alpha.sa", "text": "dental"}]})

    gateway = ProviderGateway()
    build_from_config(_cfg(REST_SEARCH), gateway=gateway,
                      transport=httpx.MockTransport(handler))
    [adapter] = gateway.adapters(Capability.SEARCH_COMPANIES)
    assert adapter.spec.provider_id == "acme-search"
    assert adapter.spec.priority == 15
    res = adapter.call("search_companies", {"query": "dental riyadh", "max_results": 3})
    assert res.ok
    assert res.data["results"] == [
        {"title": "Alpha", "url": "https://alpha.sa", "snippet": "dental",
         "provider": "acme-search"}]
    assert seen["auth"] == "Bearer k1"
    import json
    assert json.loads(seen["body"]) == {"q": "dental riyadh", "limit": 3}   # limit stays an int


def test_missing_key_means_tool_is_not_registered(monkeypatch):
    monkeypatch.delenv("ACME_API_KEY", raising=False)
    gateway = ProviderGateway()
    report = build_from_config(_cfg(REST_SEARCH), gateway=gateway)
    assert gateway.adapters(Capability.SEARCH_COMPANIES) == []
    assert report.skipped == {"acme-search": "ACME_API_KEY not set"}


def test_disabled_entry_is_skipped_even_with_key(monkeypatch):
    monkeypatch.setenv("ACME_API_KEY", "k1")
    gateway = ProviderGateway()
    entry = {**REST_SEARCH, "enabled": False}
    report = build_from_config(_cfg(entry), gateway=gateway)
    assert gateway.adapters(Capability.SEARCH_COMPANIES) == []
    assert report.skipped == {"acme-search": "disabled"}


def test_priority_from_config_orders_the_waterfall(monkeypatch):
    monkeypatch.setenv("ACME_API_KEY", "k1")
    monkeypatch.setenv("OTHER_API_KEY", "k2")
    other = {**REST_SEARCH, "id": "other", "priority": 5, "env_key": "OTHER_API_KEY"}
    gateway = ProviderGateway()
    build_from_config(_cfg(REST_SEARCH, other), gateway=gateway)
    ids = [a.spec.provider_id for a in gateway.adapters(Capability.SEARCH_COMPANIES)]
    assert ids == ["other", "acme-search"]


def test_builtin_vendor_kind_reuses_existing_adapter(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "t1")
    entry = {"id": "tavily", "kind": "builtin", "builtin": "tavily",
             "capability": "search_companies", "priority": 7, "enabled": True,
             "env_key": "TAVILY_API_KEY"}
    gateway = ProviderGateway()
    build_from_config(_cfg(entry), gateway=gateway)
    [adapter] = gateway.adapters(Capability.SEARCH_COMPANIES)
    assert adapter.spec.provider_id == "tavily"
    assert adapter.spec.priority == 7          # config overrides the class default


def test_key_pool_accepts_many_keys_and_rotates_on_429(monkeypatch):
    monkeypatch.setenv("ACME_API_KEY", "k1,k2,k3")
    used = []

    def handler(request: httpx.Request) -> httpx.Response:
        used.append(request.headers["authorization"])
        if len(used) < 3:
            return httpx.Response(429, json={})
        return httpx.Response(200, json={"hits": [
            {"name": "A", "link": "https://a.sa", "text": ""}]})

    gateway = ProviderGateway()
    build_from_config(_cfg(REST_SEARCH), gateway=gateway,
                      transport=httpx.MockTransport(handler))
    [adapter] = gateway.adapters(Capability.SEARCH_COMPANIES)
    assert adapter.call("search_companies", {"query": "q", "max_results": 1}).ok
    assert used == ["Bearer k1", "Bearer k2", "Bearer k3"]


def test_all_keys_exhausted_is_classified_not_raised(monkeypatch):
    monkeypatch.setenv("ACME_API_KEY", "k1,k2")
    gateway = ProviderGateway()
    build_from_config(_cfg(REST_SEARCH), gateway=gateway,
                      transport=httpx.MockTransport(lambda r: httpx.Response(429, json={})))
    [adapter] = gateway.adapters(Capability.SEARCH_COMPANIES)
    res = adapter.call("search_companies", {"query": "q", "max_results": 1})
    assert not res.ok
    assert res.failure.value == "RATE_LIMIT"      # gateway then falls to the next tool


def test_model_entry_openai_compatible(monkeypatch):
    monkeypatch.setenv("GLM_API_KEY", "g1")
    cfg = {"version": 1, "providers": [], "models": [{
        "id": "glm", "kind": "openai_compat", "capability": "reasoning",
        "priority": 5, "enabled": True, "env_key": "GLM_API_KEY",
        "settings": {"base_url": "https://glm.test/v1", "model": "glm-5.3"}}]}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer g1"
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "hello"}}],
            "usage": {"total_tokens": 12}})

    from infrastructure.models.gateway import ModelGateway

    mg = ModelGateway()
    build_from_config(cfg, model_gateway=mg, transport=httpx.MockTransport(handler))
    reply = mg.complete("reasoning", "hi")
    assert reply.text == "hello" and reply.model_id == "glm-5.3" and reply.tokens == 12


@pytest.mark.parametrize("bad, fragment", [
    ({"id": "x", "kind": "nope", "capability": "search_companies", "priority": 1,
      "env_key": "K"}, "unknown kind"),
    ({"id": "x", "kind": "rest_search", "capability": "teleport", "priority": 1,
      "env_key": "K", "settings": {}}, "unknown capability"),
    ({"kind": "rest_search", "capability": "search_companies", "priority": 1,
      "env_key": "K", "settings": {}}, "missing 'id'"),
])
def test_bad_entries_fail_loudly_at_load(bad, fragment):
    with pytest.raises(RegistryConfigError) as exc:
        build_from_config(_cfg(bad), gateway=ProviderGateway())
    assert fragment in str(exc.value)


def test_duplicate_ids_rejected():
    with pytest.raises(RegistryConfigError) as exc:
        build_from_config(_cfg(REST_SEARCH, REST_SEARCH), gateway=ProviderGateway())
    assert "duplicate id" in str(exc.value)


def test_load_returns_none_when_file_absent(tmp_path):
    assert load_registry_config(tmp_path / "providers.yaml") is None


def test_load_parses_yaml(tmp_path):
    p = tmp_path / "providers.yaml"
    p.write_text("version: 1\nproviders: []\nmodels: []\n")
    assert load_registry_config(p) == {"version": 1, "providers": [], "models": []}


def test_secrets_never_appear_in_report(monkeypatch):
    monkeypatch.setenv("ACME_API_KEY", "super-secret-value")
    report = build_from_config(_cfg(REST_SEARCH), gateway=ProviderGateway())
    assert "super-secret-value" not in repr(report)
    assert report.registered == ["acme-search"]


# ---------------------------------------------------------------- bootstrap
def _write(tmp_path, text):
    p = tmp_path / "providers.yaml"
    p.write_text(text)
    return p


def _ids(gateway):
    return sorted(a.spec.provider_id for c in Capability for a in gateway.adapters(c))


def test_bootstrap_without_file_is_unchanged(monkeypatch, tmp_path):
    from infrastructure.providers import bootstrap, registry

    monkeypatch.setenv("LEAD_ENGINE_V6_PROVIDERS", "real")
    monkeypatch.setenv("TAVILY_API_KEY", "t")
    monkeypatch.setattr(registry, "DEFAULT_PATH", tmp_path / "missing.yaml")
    assert _ids(bootstrap.build_gateway()) == ["smtp-verify", "tavily"]


def test_bootstrap_adds_file_tools_beside_builtins(monkeypatch, tmp_path):
    from infrastructure.providers import bootstrap, registry

    monkeypatch.setenv("LEAD_ENGINE_V6_PROVIDERS", "real")
    monkeypatch.setenv("TAVILY_API_KEY", "t")
    monkeypatch.setenv("ACME_API_KEY", "a")
    monkeypatch.setattr(registry, "DEFAULT_PATH", _write(tmp_path, """
version: 1
providers:
  - {id: tavily, kind: builtin, capability: search_companies, priority: 1}
  - id: acme-search
    kind: rest_search
    capability: search_companies
    priority: 15
    env_key: ACME_API_KEY
    settings: {url: "https://api.acme.test/s"}
models: []
"""))
    gw = bootstrap.build_gateway()
    # tavily is NOT duplicated by the file; acme-search is added next to it
    assert _ids(gw) == ["acme-search", "smtp-verify", "tavily"]
    order = [a.spec.provider_id for a in gw.adapters(Capability.SEARCH_COMPANIES)]
    assert order == ["tavily", "acme-search"]


def test_bootstrap_registers_file_model_ahead_of_fake(monkeypatch, tmp_path):
    from infrastructure.providers import bootstrap, registry

    monkeypatch.setenv("GLM_API_KEY", "g")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(registry, "DEFAULT_PATH", _write(tmp_path, """
version: 1
providers: []
models:
  - id: glm
    kind: openai_compat
    capability: reasoning
    priority: 5
    env_key: GLM_API_KEY
    settings: {base_url: "https://glm.test/v1", model: glm-5.3}
"""))
    mg = bootstrap.build_model_gateway()
    models = [type(a).__name__ for _, a in mg._adapters["reasoning"]]
    assert models == ["OpenAICompatModel", "FakeModel"]


def test_malformed_file_fails_loudly_at_boot(monkeypatch, tmp_path):
    from infrastructure.providers import bootstrap, registry

    monkeypatch.setenv("LEAD_ENGINE_V6_PROVIDERS", "real")
    monkeypatch.setattr(registry, "DEFAULT_PATH", _write(tmp_path, """
version: 1
providers:
  - {id: x, kind: telepathy, capability: search_companies, priority: 1, env_key: K}
models: []
"""))
    with pytest.raises(RegistryConfigError):
        bootstrap.build_gateway()


def test_shipped_config_file_is_valid_and_inert():
    """The committed config/providers.yaml must load and add nothing by itself."""
    cfg = load_registry_config()
    assert cfg is not None
    report = build_from_config(cfg, gateway=ProviderGateway())
    assert report.registered == []
