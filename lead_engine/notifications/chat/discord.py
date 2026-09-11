"""Discord webhook sender using embed JSON.

Discord webhooks accept a JSON body with optional ``embeds`` array.
We always send a single indigo-colored embed with optional fields.
"""
from .base import WebhookSender


class DiscordSender(WebhookSender):
    """Format messages for Discord incoming webhooks (embed JSON).

    Reference: https://discord.com/developers/docs/resources/webhook
    """

    # Indigo: 0x58, 0x14, 0x7F == 5814783
    DEFAULT_COLOR = 5814783

    def format_payload(self, title: str, message: str,
                       fields: dict | None = None) -> dict:
        embed = {
            "title": title,
            "description": message,
            "color": self.DEFAULT_COLOR,
        }
        if fields:
            embed["fields"] = [
                {"name": k, "value": str(v), "inline": False}
                for k, v in fields.items()
            ]
        return {"embeds": [embed]}
