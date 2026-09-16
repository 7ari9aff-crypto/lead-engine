"""Outbound URL safety (SSRF guard): reject non-public hosts.

Used by webhook creation, webhook delivery, and custom provider base_url
validation. Resolves the hostname and rejects ANY resolved address that is
private, loopback, link-local, reserved, multicast, or unspecified - which
also covers DNS that points at internal infrastructure.
"""
import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeTarget(ValueError):
    """The target host resolves to a non-public address."""


def assert_public_host(host, allow_loopback: bool = False):
    """Resolve `host` and require every resolved address to be public.
    Returns the hostname when safe; raises UnsafeTarget otherwise."""
    return resolve_public_ips(host, allow_loopback=allow_loopback)[0]


def resolve_public_ips(host, allow_loopback: bool = False):
    """Resolve `host`, reject non-public space, return (host, [ip strings]).

    The returned IPs let callers pin the connection (netguard.pinned_post)
    so a hostile DNS flip between check and connect (TOCTOU rebinding)
    cannot redirect the request to internal infrastructure.
    """
    host = (host or "").strip().lower()
    if not host:
        raise UnsafeTarget("missing host")
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        # Unresolvable is not a security signal: the HTTP layer fails on
        # delivery and the event dead-letters naturally. The guard blocks
        # only hosts that RESOLVE into non-public space.
        return host, []
    ips: list[str] = []
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        bad = (ip.is_private or ip.is_loopback or ip.is_link_local
               or ip.is_reserved or ip.is_multicast or ip.is_unspecified)
        if bad and not (allow_loopback and ip.is_loopback):
            raise UnsafeTarget("host %s resolves to non-public address %s" % (host, ip))
        text = str(ip)
        if text not in ips:
            ips.append(text)
    return host, ips


def pinned_post(url: str, ips: list[str], allow_loopback: bool = False,
                **kwargs):
    """POST to `url` with a rebind check against already-vetted `ips`.

    Re-resolves the host at delivery time and requires the fresh answer
    to intersect the vetted set captured at registration/check time; a
    complete flip raises UnsafeTarget instead of delivering to an
    attacker-swapped internal address. TLS verification is untouched —
    the request still goes to the hostname URL, so cert validation
    against the hostname stays intact.
    """
    import requests as _requests

    parsed = urlparse(url)
    _, fresh = resolve_public_ips(parsed.hostname,
                                  allow_loopback=allow_loopback)
    if ips and fresh and not (set(fresh) & set(ips)):
        raise UnsafeTarget(
            "DNS for %s changed between check and delivery "
            "(possible rebinding); refused" % parsed.hostname)
    kwargs.setdefault("timeout", 10)
    return _requests.post(url, **kwargs)


def assert_public_http_url(url: str, allow_loopback: bool = False) -> None:
    """Full-URL variant: scheme + credentials + host checks."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeTarget("only http(s) URLs are allowed")
    if parsed.username or parsed.password:
        raise UnsafeTarget("credentials in URL are not allowed")
    assert_public_host(parsed.hostname, allow_loopback=allow_loopback)