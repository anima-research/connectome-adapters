from dataclasses import dataclass, field
from typing import Set

from src.core.conversation.base_data_classes import BaseConversationInfo

@dataclass
class ConversationInfo(BaseConversationInfo):
    """Comprehensive information about a Slack conversation"""
    messages: Set[str] = field(default_factory=set)

    # Add pinned message tracking
    pinned_messages: Set[str] = field(default_factory=set)
