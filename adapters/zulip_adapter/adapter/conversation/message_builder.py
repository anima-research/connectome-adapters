from typing import Any
from core.conversation.base_message_builder import BaseMessageBuilder

class MessageBuilder(BaseMessageBuilder):
    """Builds message objects from Zulip events"""

    def with_basic_info(self, message: Any, conversation_id: str) -> 'MessageBuilder':
        """Add basic message info"""
        self.message_data["message_id"] = str(message["id"]) if message.get("id", None) else None
        self.message_data["conversation_id"] = conversation_id
        self.message_data["timestamp"] = message.get("timestamp", None)
        return self

    def with_content(self, message: Any) -> 'MessageBuilder':
        """Add message content"""
        self.message_data["text"] = message.get("content", None)
        return self
