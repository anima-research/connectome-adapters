from dataclasses import dataclass, field
from typing import Optional, Set

@dataclass
class ConversationInfo():
    """Basic information about a Discord webhook conversation"""
    # Core identifiers
    conversation_id: str  # Typically the channel ID for Discord webhooks

    # Message tracking
    messages: Set[str] = field(default_factory=set)
    message_count: int = 0  # Count of messages sent

    # Webhook-specific data
    webhook_url: Optional[str] = None  # The webhook URL for this conversation
    webhook_name: Optional[str] = None  # Default name for the webhook
