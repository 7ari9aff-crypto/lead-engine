"""Microsoft Teams incoming-webhook sender using the MessageCard format.

Office 365 connectors accept the legacy ``MessageCard`` schema via the
``/webhookb2/{group}@{tenant}/IncomingWebhook/{channel}/...`` URL.
"""
from .base import WebhookSender


class TeamsSender(WebhookSender):
    """Format messages for Microsoft Teams incoming webhooks (MessageCard).

    Reference: https://learn.microsoft.com/en-us/outlook/actionable-messages/message-card-reference
    """

    DEFAULT_THEME_COLOR = "5B4FE9"  # indigo

    def format_payload(self, title: str, message: str,
                       fields: dict | None = None) -> dict:
        card = {
            "@type": "MessageCard",
            "@context": "https://schema.org/extensions",
            "summary": title,
            "themeColor": self.DEFAULT_THEME_COLOR,
            "title": title,
            "text": message,
        }
        if fields:
            card["facts"] = [
                {"name": k, "value": str(v)} for k, v in fields.items()
            ]
        return card
