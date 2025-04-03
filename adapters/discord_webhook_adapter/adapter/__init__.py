"""Discord adapter implementation."""

from adapters.discord_webhook_adapter.adapter.adapter import Adapter
from adapters.discord_webhook_adapter.adapter.discord_webhook_client import DiscordWebhookClient

__all__ = [
    "Adapter",
    "DiscordWebhookClient"
]
