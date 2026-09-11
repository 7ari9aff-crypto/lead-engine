"""Tests for chat webhook senders (Slack, Discord, Teams).

Each sender is exercised for:
- payload shape (platform-specific JSON structure)
- fields are included when provided
- send() returns ok=True on 2xx (mocked urlopen)
- send() returns ok=False on HTTPError, URLError, TimeoutError, OSError

urlopen is mocked per-test via ``unittest.mock.patch`` so no real HTTP
traffic is generated.
"""
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError, URLError

import pytest

from lead_engine.notifications.chat import (
    SlackSender,
    DiscordSender,
    TeamsSender,
    WebhookSender,
)


# ---------------------------------------------------------------------- Slack
class TestSlackSender:
    def test_payload_has_blocks_with_header_and_section(self):
        payload = SlackSender("https://hooks.slack.test/x").format_payload(
            "Title", "Body text"
        )
        assert "blocks" in payload
        assert isinstance(payload["blocks"], list)
        header = payload["blocks"][0]
        section = payload["blocks"][1]
        assert header["type"] == "header"
        assert header["text"]["type"] == "plain_text"
        assert header["text"]["text"] == "Title"
        assert section["type"] == "section"
        assert section["text"]["type"] == "mrkdwn"
        assert section["text"]["text"] == "Body text"

    def test_payload_omits_fields_block_when_none(self):
        payload = SlackSender("https://hooks.slack.test/x").format_payload(
            "T", "M"
        )
        assert len(payload["blocks"]) == 2

    def test_payload_includes_fields_block_when_provided(self):
        fields = {"User": "Alice", "Score": "0.91"}
        payload = SlackSender("https://hooks.slack.test/x").format_payload(
            "T", "M", fields=fields
        )
        assert len(payload["blocks"]) == 3
        field_block = payload["blocks"][2]
        assert field_block["type"] == "section"
        rendered = {f["text"] for f in field_block["fields"]}
        assert "*User*\nAlice" in rendered
        assert "*Score*\n0.91" in rendered

    def test_send_returns_ok_true_on_2xx(self):
        sender = SlackSender("https://hooks.slack.test/x")
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("lead_engine.notifications.chat.base.urlopen",
                   return_value=mock_resp):
            result = sender.send({"blocks": []})
        assert result == {"ok": True}

    def test_send_returns_ok_false_on_http_error(self):
        sender = SlackSender("https://hooks.slack.test/x")
        with patch("lead_engine.notifications.chat.base.urlopen",
                   side_effect=HTTPError(
                       "https://hooks.slack.test/x", 500,
                       "Internal Server Error", {}, None)):
            result = sender.send({"blocks": []})
        assert result["ok"] is False
        assert "error" in result
        assert isinstance(result["error"], str)

    def test_send_returns_ok_false_on_url_error(self):
        sender = SlackSender("https://hooks.slack.test/x")
        with patch("lead_engine.notifications.chat.base.urlopen",
                   side_effect=URLError("dns failure")):
            result = sender.send({"blocks": []})
        assert result["ok"] is False
        assert "error" in result


# --------------------------------------------------------------------- Discord
class TestDiscordSender:
    def test_payload_has_embeds_with_title_and_description(self):
        payload = DiscordSender("https://discord.test/x").format_payload(
            "Hello", "World"
        )
        assert "embeds" in payload
        assert isinstance(payload["embeds"], list)
        embed = payload["embeds"][0]
        assert embed["title"] == "Hello"
        assert embed["description"] == "World"
        assert embed["color"] == 5814783
        assert "fields" not in embed

    def test_payload_includes_fields_when_provided(self):
        fields = {"Lead": "Acme", "Score": "0.7"}
        payload = DiscordSender("https://discord.test/x").format_payload(
            "T", "M", fields=fields
        )
        embed = payload["embeds"][0]
        assert embed["fields"] == [
            {"name": "Lead", "value": "Acme", "inline": False},
            {"name": "Score", "value": "0.7", "inline": False},
        ]

    def test_send_returns_ok_true_on_2xx(self):
        sender = DiscordSender("https://discord.test/x")
        mock_resp = MagicMock()
        mock_resp.status = 204
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("lead_engine.notifications.chat.base.urlopen",
                   return_value=mock_resp):
            result = sender.send({"embeds": []})
        assert result == {"ok": True}

    def test_send_returns_ok_false_on_http_error(self):
        sender = DiscordSender("https://discord.test/x")
        with patch("lead_engine.notifications.chat.base.urlopen",
                   side_effect=HTTPError(
                       "https://discord.test/x", 429,
                       "Too Many Requests", {}, None)):
            result = sender.send({"embeds": []})
        assert result["ok"] is False
        assert "error" in result

    def test_send_returns_ok_false_on_url_error(self):
        sender = DiscordSender("https://discord.test/x")
        with patch("lead_engine.notifications.chat.base.urlopen",
                   side_effect=URLError("connection refused")):
            result = sender.send({"embeds": []})
        assert result["ok"] is False
        assert "error" in result


# ---------------------------------------------------------------------- Teams
class TestTeamsSender:
    def test_payload_is_messagecard_with_title(self):
        payload = TeamsSender("https://teams.test/x").format_payload(
            "Summary", "Details"
        )
        assert payload["@type"] == "MessageCard"
        assert payload["@context"] == "https://schema.org/extensions"
        assert payload["title"] == "Summary"
        assert payload["text"] == "Details"
        assert payload["summary"] == "Summary"
        assert payload["themeColor"] == "5B4FE9"
        assert "facts" not in payload

    def test_payload_includes_facts_when_provided(self):
        fields = {"Region": "Riyadh", "Tier": "Gold"}
        payload = TeamsSender("https://teams.test/x").format_payload(
            "T", "M", fields=fields
        )
        assert payload["facts"] == [
            {"name": "Region", "value": "Riyadh"},
            {"name": "Tier", "value": "Gold"},
        ]

    def test_send_returns_ok_true_on_2xx(self):
        sender = TeamsSender("https://teams.test/x")
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("lead_engine.notifications.chat.base.urlopen",
                   return_value=mock_resp):
            result = sender.send({"@type": "MessageCard"})
        assert result == {"ok": True}

    def test_send_returns_ok_false_on_http_error(self):
        sender = TeamsSender("https://teams.test/x")
        with patch("lead_engine.notifications.chat.base.urlopen",
                   side_effect=HTTPError(
                       "https://teams.test/x", 500,
                       "Server Error", {}, None)):
            result = sender.send({"@type": "MessageCard"})
        assert result["ok"] is False
        assert "error" in result

    def test_send_returns_ok_false_on_url_error(self):
        sender = TeamsSender("https://teams.test/x")
        with patch("lead_engine.notifications.chat.base.urlopen",
                   side_effect=URLError("network unreachable")):
            result = sender.send({"@type": "MessageCard"})
        assert result["ok"] is False
        assert "error" in result


# ----------------------------------------------------------------------- base
class TestWebhookSenderBase:
    """Direct tests of the abstract base class contract."""

    def test_base_is_abstract(self):
        with pytest.raises(TypeError):
            WebhookSender("https://x.test/abc")  # type: ignore[abstract]

    def test_send_returns_ok_false_on_timeout(self):
        class StubSender(WebhookSender):
            def format_payload(self, title, message, fields=None):
                return {"stub": True}

        sender = StubSender("https://x.test/abc")
        with patch("lead_engine.notifications.chat.base.urlopen",
                   side_effect=TimeoutError("read timed out")):
            result = sender.send({"stub": True})
        assert result["ok"] is False
        assert "read timed out" in result["error"]

    def test_send_returns_ok_false_on_os_error(self):
        class StubSender(WebhookSender):
            def format_payload(self, title, message, fields=None):
                return {"stub": True}

        sender = StubSender("https://x.test/abc")
        with patch("lead_engine.notifications.chat.base.urlopen",
                   side_effect=OSError("broken pipe")):
            result = sender.send({"stub": True})
        assert result["ok"] is False
        assert "broken pipe" in result["error"]
