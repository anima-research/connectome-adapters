from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime

from src.core.cache.cache import Cache
from src.core.conversation.base_data_classes import ThreadInfo

class BaseMessageBuilder(ABC):
    """Builds message objects from adapter events"""

    def __init__(self):
        self.reset()

    def reset(self):
        """Reset the builder to its initial state"""
        self.message_data = {}
        return self

    def with_sender_id(self, sender_id: str) -> 'BaseMessageBuilder':
        """Add sender information"""
        sender = Cache.get_instance().user_cache.get_user_by_id(sender_id)

        if sender:
            self.message_data["sender_id"] = sender_id
            self.message_data["sender_name"] = sender.display_name
            self.message_data["is_from_bot"] = sender.is_bot

        return self

    def with_thread_info(self, thread_info: ThreadInfo) -> 'BaseMessageBuilder':
        """Add thread information"""
        if thread_info:
            self.message_data["thread_id"] = thread_info.thread_id
            self.message_data["reply_to_message_id"] = thread_info.thread_id
        return self

    def build(self) -> Dict[str, Any]:
        """Build the final message object"""
        return self.message_data.copy()

    @abstractmethod
    def with_basic_info(self, message: Any, conversation_id: str) -> 'BaseMessageBuilder':
        """Add basic message info"""
        raise NotImplementedError("Child classes must implement with_basic_info")

    @abstractmethod
    def with_content(self, event: Any) -> 'BaseMessageBuilder':
        """Add message content"""
        raise NotImplementedError("Child classes must implement with_content")
