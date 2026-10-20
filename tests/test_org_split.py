"""E4 regression: v1 and v6 are different tenants and need different org ids.

LEAD_ENGINE_ORG_ID is the v1 (engine.*) org "Lead Engine". v6 (platform.*,
runtime.*) has its own org "Production Org". One shared variable meant either
v1's worker was blind to its jobs (RLS) or v6's cookie owners landed in the
wrong tenant. v6 now reads LEAD_ENGINE_V6_ORG_ID first and only falls back to
the shared variable, so existing deployments keep working unchanged.
"""
from v6api import bridge


V1 = "fc4505fe-382e-4df9-bc2a-f97ae17590db"
V6 = "96773dcc-73ed-41be-b2c3-7800eabb04cc"


def test_v6_prefers_its_own_org(monkeypatch):
    monkeypatch.setenv("LEAD_ENGINE_ORG_ID", V1)
    monkeypatch.setenv("LEAD_ENGINE_V6_ORG_ID", V6)
    assert bridge.v6_org_bridge() == V6


def test_v6_falls_back_to_shared_variable(monkeypatch):
    monkeypatch.setenv("LEAD_ENGINE_ORG_ID", V1)
    monkeypatch.delenv("LEAD_ENGINE_V6_ORG_ID", raising=False)
    assert bridge.v6_org_bridge() == V1


def test_blank_v6_variable_does_not_mask_the_fallback(monkeypatch):
    monkeypatch.setenv("LEAD_ENGINE_ORG_ID", V1)
    monkeypatch.setenv("LEAD_ENGINE_V6_ORG_ID", "   ")
    assert bridge.v6_org_bridge() == V1


def test_unset_everywhere_is_empty_not_none(monkeypatch):
    monkeypatch.delenv("LEAD_ENGINE_ORG_ID", raising=False)
    monkeypatch.delenv("LEAD_ENGINE_V6_ORG_ID", raising=False)
    assert bridge.v6_org_bridge() == ""
