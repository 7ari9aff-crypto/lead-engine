"""Composition helpers for entrypoints (apps.api / apps.worker).

Provider selection (env LEAD_ENGINE_V6_PROVIDERS):
  auto (default) — real adapters when their API keys exist, fakes otherwise
  demo           — deterministic demo providers (offline dev/tests)
  real           — real adapters only (fail loudly when keys are missing)
"""
from __future__ import annotations

import os

from infrastructure.models.gateway import FakeModel, ModelGateway
from infrastructure.providers.fakes import (
    FakeContactProvider,
    FakeSearchProvider,
    FakeVerifyProvider,
)
from infrastructure.providers.gateway import ProviderGateway

DEMO_SEARCH_RESULTS = [
    {"always": True, "url": "https://alpha-dental.sa", "title": "Alpha Dental Clinic",
     "snippet": "dental clinic in Riyadh"},
    {"always": True, "url": "https://beta-clinic.sa/en", "title": "Beta Clinic",
     "snippet": "dental services Riyadh"},
    {"always": True, "url": "https://facebook.com/riyadh-dental", "title": "Dental page",
     "snippet": "social page"},
    {"always": True, "url": "https://news.example.com/best-dental", "title": "Best dental clinics 2026",
     "snippet": "article"},
]
DEMO_CONTACTS = {
    "alpha-dental.sa": [{"name": "Dr. Sara", "role": "owner",
                         "email": "info@alpha-dental.sa", "phone": "+966500000001"}],
    "beta-clinic.sa": [{"name": "Mr. Khaled", "role": "manager",
                        "email": "office@beta-clinic.sa"}],
}
DEMO_VERIFY = {"info@alpha-dental.sa": "DELIVERABLE", "office@beta-clinic.sa": "CATCH_ALL"}


def _key(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _ensure_env_loaded() -> None:
    from infrastructure.config import ENV_FILE, _load_env_file

    _load_env_file(ENV_FILE)


def _mode() -> str:
    mode = (os.environ.get("LEAD_ENGINE_V6_PROVIDERS") or "auto").strip().lower()
    if mode == "auto":
        has_real = bool(_key("TAVILY_API_KEY") or _key("EXA_API_KEY"))
        return "real" if has_real else "demo"
    return mode


def build_gateway() -> ProviderGateway:
    _ensure_env_loaded()
    gateway = ProviderGateway()
    mode = _mode()
    if mode in ("demo", "auto"):
        gateway.register(FakeSearchProvider("demo-search", priority=90,
                                            results=DEMO_SEARCH_RESULTS))
        gateway.register(FakeVerifyProvider("demo-verify", priority=90,
                                            mapping=DEMO_VERIFY))
        gateway.register(FakeContactProvider(contacts_by_domain=DEMO_CONTACTS, priority=90))
    if mode in ("real", "auto"):
        from infrastructure.providers.real import (
            ApolloContactAdapter,
            ExaSearchAdapter,
            HunterContactAdapter,
            HunterVerifyAdapter,
            SmtpVerifyAdapter,
            TavilySearchAdapter,
        )

        if _key("TAVILY_API_KEY"):
            gateway.register(TavilySearchAdapter())
        if _key("EXA_API_KEY"):
            gateway.register(ExaSearchAdapter())
        gateway.register(SmtpVerifyAdapter())
        # FIND_CONTACT waterfall: Apollo (0 credits) → Hunter (1 credit).
        # Without these the enrichment phase could only fail with CAPACITY —
        # the root cause of "attempted: 28, enriched: 0".
        if _key("APOLLO_API_KEY"):
            gateway.register(ApolloContactAdapter())
        if _key("HUNTER_API_KEY"):
            gateway.register(HunterContactAdapter())
        # VERIFY_EMAIL waterfall: SMTP probe first, Hunter second hop —
        # catch-all/ambiguous domains get a real second opinion.
        if _key("HUNTER_API_KEY"):
            gateway.register(HunterVerifyAdapter())
    _apply_registry(gateway=gateway)
    return gateway


def _apply_registry(*, gateway=None, model_gateway=None) -> None:
    """Add tools/models declared in config/providers.yaml ON TOP of the built-in
    set. Absent file = no change. A malformed file raises at boot (loud), never
    silently drops a tool."""
    import logging

    from infrastructure.providers.registry import build_from_config, load_registry_config

    config = load_registry_config()
    if config is None:
        return
    # Built-ins above already registered tavily/exa/apollo/hunter/smtp/gemini;
    # a file entry for one of those ids only re-prioritises, never duplicates.
    existing = {a.spec.provider_id for caps in
                (gateway.adapters(c) for c in _caps()) for a in caps} if gateway else set()
    config = {**config,
              "providers": [e for e in config["providers"] if e.get("id") not in existing],
              "models": [] if model_gateway is None else config["models"]}
    report = build_from_config(config, gateway=gateway, model_gateway=model_gateway)
    logging.getLogger(__name__).info(
        "registry: registered=%s skipped=%s", report.registered, report.skipped)


def _caps():
    from contracts.providers import Capability

    return list(Capability)


def build_model_gateway() -> ModelGateway:
    _ensure_env_loaded()
    model_gateway = ModelGateway()
    if _key("GEMINI_API_KEY"):
        from infrastructure.providers.real import GeminiReasonModel

        model_gateway.register("reasoning", GeminiReasonModel(), priority=10)
    model_gateway.register("reasoning", FakeModel(), priority=99)
    model_gateway.register("planning", FakeModel())
    _apply_registry(model_gateway=model_gateway)
    return model_gateway
