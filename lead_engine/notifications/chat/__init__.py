"""Chat webhook senders: Slack, Discord, Microsoft Teams.

Each sender inherits the safe HTTP POST wrapper from
``WebhookSender`` and only needs to implement ``format_payload`` for its
platform's native JSON schema (Block Kit, embed, MessageCard).
"""
from .base import WebhookSender
from .slack import SlackSender
from .discord import DiscordSender
from .teams import TeamsSender

__all__ = [
    "WebhookSender",
    "SlackSender",
    "DiscordSender",
    "TeamsSender",
]
