"""Abstract base for webhook-based chat notifications.

Each concrete sender (Slack, Discord, Teams) formats its own JSON payload
and inherits the safe HTTP POST wrapper from WebhookSender. The wrapper
never raises — it always returns a dict so callers can dispatch / log
results without try/except plumbing.
"""
from abc import ABC, abstractmethod
import json
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


class WebhookSender(ABC):
    def __init__(self, webhook_url: str, timeout: float = 10.0):
        self.webhook_url = webhook_url
        self.timeout = timeout

    @abstractmethod
    def format_payload(self, title: str, message: str,
                       fields: dict | None = None) -> dict: ...

    def send(self, payload: dict) -> dict:
        """POST ``payload`` as JSON to the webhook URL.

        Returns ``{"ok": True}`` on any 2xx response, otherwise
        ``{"ok": False, "error": "<message>"}``. Never raises — all
        network / HTTP errors are normalized to the error dict so
        callers can branch on ``ok`` instead of try/except.
        """
        try:
            body = json.dumps(payload).encode("utf-8")
            request = Request(
                self.webhook_url,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=self.timeout) as response:
                # urlopen raises HTTPError on 4xx/5xx; reaching here means 2xx.
                _ = response.status  # touch attr to prove no exception was masked
            return {"ok": True}
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            return {"ok": False, "error": str(exc)}
