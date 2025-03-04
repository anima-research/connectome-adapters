from dataclasses import dataclass, field
from typing import Optional, Set

from core.conversation.base_data_classes import BaseConversationInfo

@dataclass
class ConversationInfo(BaseConversationInfo):
    """Comprehensive information about a Telegram chat"""
    # Add pinned message tracking
    pinned_messages: Set[str] = field(default_factory=set)
