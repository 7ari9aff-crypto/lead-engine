import pytest

from lead_engine.netguard import (
    UnsafeTarget,
    assert_public_host,
    pinned_post,
    resolve_public_ips,
)
from lead_engine.ratelimit import RateLimiter


def test_private_ip_rejected():
    with pytest.raises(UnsafeTarget):
        assert_public_host("10.1.2.3")


def test_linklocal_metadata_rejected():
    with pytest.raises(UnsafeTarget):
        assert_public_host("169.254.169.254")


def test_loopback_rejected_unless_allowed():
    with pytest.raises(UnsafeTarget):
        assert_public_host("127.0.0.1")
    assert assert_public_host("127.0.0.1", allow_loopback=True) == "127.0.0.1"


def test_public_ip_allowed():
    # numeric literal: resolves without network access (deterministic in CI)
    assert assert_public_host("8.8.8.8") == "8.8.8.8"


def test_resolve_public_ips_returns_vetted_set():
    host, ips = resolve_public_ips("8.8.8.8")
    assert host == "8.8.8.8"
    assert "8.8.8.8" in ips


def test_pinned_post_refuses_rebound_dns(monkeypatch):
    import lead_engine.netguard as ng

    def fake_resolve(host, allow_loopback=False):
        return host, ["9.9.9.9"]  # fresh answer no longer intersects vetted

    monkeypatch.setattr(ng, "resolve_public_ips", fake_resolve)
    with pytest.raises(UnsafeTarget):
        pinned_post("http://example.com/hook", ["1.1.1.1"])


def test_rate_limiter_throttles_and_recovers():
    limiter = RateLimiter(rps=2.0, burst=2.0)
    scope = {"type": "http", "method": "GET", "path": "/api/v1/leads",
             "headers": [], "client": ("9.9.9.9", 1234)}
    assert limiter.allow(scope)[0] is True
    assert limiter.allow(scope)[0] is True
    allowed, retry_after = limiter.allow(scope)
    assert allowed is False and retry_after >= 1


def test_rate_limiter_exempts_probes_and_machine_clients(monkeypatch):
    import os

    monkeypatch.setenv("LEAD_ENGINE_MCP_TOKEN", "machine-secret")
    limiter = RateLimiter(rps=1.0, burst=1.0)
    probe = {"type": "http", "method": "GET", "path": "/health",
             "headers": [], "client": ("9.9.9.9", 1234)}
    machine = {"type": "http", "method": "GET", "path": "/api/v1/leads",
               "headers": [(b"authorization", b"Bearer machine-secret")],
               "client": ("9.9.9.9", 1234)}
    assert limiter.allow(probe) == (True, 0)
    assert limiter.allow(machine) == (True, 0)
    assert os.environ.get("LEAD_ENGINE_MCP_TOKEN") == "machine-secret"