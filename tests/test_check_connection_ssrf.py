"""check_connection must not probe internal addresses or follow redirects."""
from unittest.mock import patch

from lead_engine.agent_registry import AgentRegistry


class _DB:
    def __init__(self, base_url):
        self.row = {"name": "p", "env_key": None, "base_url": base_url, "priority": 1}
        self.updates = []

    def one(self, sql, params=()):
        return self.row

    def execute(self, sql, params=()):
        self.updates.append(params)


def _run(base_url):
    db = _DB(base_url)
    with patch("lead_engine.agent_registry.requests.head") as head:
        head.return_value.status_code = 200
        result = AgentRegistry(db).check_connection("p")
    return result, head


def test_internal_target_is_blocked_and_never_requested():
    for url in ("http://127.0.0.1:8000/", "http://169.254.169.254/latest/meta-data/",
                "http://localhost/", "http://10.0.0.5/"):
        result, head = _run(url)
        assert result["status"] == "blocked_unsafe_target", url
        head.assert_not_called()


def test_non_http_scheme_is_blocked():
    result, head = _run("file:///etc/passwd")
    assert result["status"] == "blocked_unsafe_target"
    head.assert_not_called()


def test_public_target_checked_without_following_redirects():
    with patch("lead_engine.netguard.socket.getaddrinfo",
               return_value=[(2, 1, 6, "", ("93.184.216.34", 0))]):
        result, head = _run("https://example.com/")
    assert result["status"] == "healthy"
    assert head.call_args.kwargs["allow_redirects"] is False
