"""Discord conversation manager implementation."""

from src.adapters.discord_webhook_adapter.conversation.data_classes import ConversationInfo
from src.adapters.discord_webhook_adapter.conversation.manager import Manager

__all__ = [
    "ConversationInfo",
    "Manager"
]
