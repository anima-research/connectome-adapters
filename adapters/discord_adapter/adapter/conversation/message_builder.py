from typing import Any
from datetime import datetime
from core.conversation.base_message_builder import BaseMessageBuilder

class MessageBuilder(BaseMessageBuilder):
    """Builds message objects from Discord events"""

    def with_basic_info(self, message: Any, conversation: Any) -> 'MessageBuilder':
        """Add basic message info"""
        self.message_data["message_id"] = str(getattr(message, "id", ""))
        self.message_data["conversation_id"] = conversation.conversation_id
        self.message_data["timestamp"] = int(getattr(message, "created_at", datetime.now()).timestamp() * 1e3)
        self.message_data["is_direct_message"] = conversation.conversation_type == "dm"
        return self

    def with_content(self, message: Any) -> 'MessageBuilder':
        """Add message content"""
        self.message_data["text"] = getattr(message, "content", None)
        return self
