"""Discord adapter implementation."""

from src.adapters.discord_webhook_adapter.adapter import Adapter
from src.adapters.discord_webhook_adapter.client import Client

__all__ = [
    "Adapter",
    "Client"
]
