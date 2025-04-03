"""Discord conversation manager implementation."""

from adapters.discord_webhook_adapter.adapter.conversation.data_classes import ConversationInfo
from adapters.discord_webhook_adapter.adapter.conversation.manager import Manager

__all__ = [
    "ConversationInfo",
    "Manager"
]
