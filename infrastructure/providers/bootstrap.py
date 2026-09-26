"""Composition helpers for entrypoints (apps.api / apps.worker)."""
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


def build_gateway() -> ProviderGateway:
    """Demo/offline gateways until real adapters are enabled; the contract
    (capability + waterfall + ledger) is identical to the production one."""
    gateway = ProviderGateway()
    if os.environ.get("LEAD_ENGINE_V6_DEMO") == "1":
        gateway.register(FakeSearchProvider("demo-search", priority=10,
                                            results=DEMO_SEARCH_RESULTS))
        gateway.register(FakeVerifyProvider("demo-verify", priority=10,
                                            mapping=DEMO_VERIFY))
        gateway.register(FakeContactProvider(contacts_by_domain=DEMO_CONTACTS))
    else:
        gateway.register(FakeSearchProvider("fake-search", priority=10, results=[]))
        gateway.register(FakeVerifyProvider("fake-verify", priority=10))
    return gateway


def build_model_gateway() -> ModelGateway:
    model_gateway = ModelGateway()
    model_gateway.register("planning", FakeModel())
    return model_gateway
