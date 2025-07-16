from typing import Any
from src.core.conversation.base_message_builder import BaseMessageBuilder

class MessageBuilder(BaseMessageBuilder):
    """Builds message objects from Zulip events"""

    def with_basic_info(self, message: Any, conversation: Any) -> 'MessageBuilder':
        """Add basic message info"""
        self.message_data["message_id"] = str(message["id"]) if message.get("id", None) else None
        self.message_data["conversation_id"] = conversation.conversation_id
        self.message_data["timestamp"] = message.get("timestamp", None)
        self.message_data["is_direct_message"] = conversation.conversation_type == "private"
        self.message_data["edit_timestamp"] = message.get("last_edit_timestamp", None)
        self.message_data["edited"] = self.message_data["edit_timestamp"] is not None
        return self

    def with_content(self, event: Any) -> 'MessageBuilder':
        """Add message content"""
        if "updated_content" in event and event["updated_content"]:
            self.message_data["text"] = event["updated_content"]
        else:
            self.message_data["text"] = event["message"].get("content", None)
        return self
