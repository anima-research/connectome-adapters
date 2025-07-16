from typing import Any
from src.core.conversation.base_message_builder import BaseMessageBuilder

class MessageBuilder(BaseMessageBuilder):
    """Builds message objects from Discord events"""

    def with_basic_info(self, message: Any, conversation: Any) -> 'MessageBuilder':
        """Add basic message info"""
        self.message_data["message_id"] = str(message.get("ts", ""))
        self.message_data["conversation_id"] = conversation.conversation_id
        self.message_data["timestamp"] = int(float(message.get("ts", "0")))
        self.message_data["is_direct_message"] = conversation.conversation_type == "im"

        edit_timestamp = None
        if message.get("edited", {}):
            edit_timestamp = int(float(message.get("edited", {}).get("ts", "0")))

        self.message_data["edit_timestamp"] = edit_timestamp
        self.message_data["edited"] = edit_timestamp is not None
        return self

    def with_content(self, event: Any) -> 'MessageBuilder':
        """Add message content"""
        if "updated_content" in event and event["updated_content"]:
            self.message_data["text"] = event["updated_content"]
        else:
            self.message_data["text"] = event["message"].get("text", "")

        return self
