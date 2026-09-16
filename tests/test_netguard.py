import pytest

from lead_engine.netguard import UnsafeTarget, assert_public_host


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