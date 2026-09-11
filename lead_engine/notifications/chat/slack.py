"""Slack incoming-webhook sender using Block Kit."""
from .base import WebhookSender


class SlackSender(WebhookSender):
    """Format messages for Slack incoming webhooks (Block Kit).

    Reference: https://api.slack.com/block-kit
    """

    def format_payload(self, title: str, message: str,
                       fields: dict | None = None) -> dict:
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": title},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": message},
            },
        ]
        if fields:
            blocks.append({
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*{k}*\n{v}"}
                    for k, v in fields.items()
                ],
            })
        return {"blocks": blocks}
