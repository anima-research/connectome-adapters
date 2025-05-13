from typing import Any
from core.conversation.base_message_builder import BaseMessageBuilder

class MessageBuilder(BaseMessageBuilder):
    """Builds message objects from Discord events"""

    def with_basic_info(self, message: Any, conversation_id: str) -> 'MessageBuilder':
        """Add basic message info"""
        self.message_data["message_id"] = str(message.get("ts", ""))
        self.message_data["conversation_id"] = conversation_id
        self.message_data["timestamp"] = int(float(message.get("ts", "0")) * 1e3)
        self.message_data["is_direct_message"] = message.get("subtype", None) is None
        return self

    def with_content(self, message: Any) -> 'MessageBuilder':
        """Add message content"""
        self.message_data["text"] = message.get("text", "")
        return self
