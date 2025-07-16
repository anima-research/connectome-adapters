from datetime import datetime
from typing import Any, Optional

from src.core.conversation.base_data_classes import UserInfo
from src.core.conversation.base_message_builder import BaseMessageBuilder

class MessageBuilder(BaseMessageBuilder):
    """Builds message objects from Telethon events"""

    def with_basic_info(self, message: Any, conversation: Any) -> 'MessageBuilder':
        """Add basic message info"""
        self.message_data["message_id"] = str(message.id)
        self.message_data["conversation_id"] = conversation.conversation_id
        self.message_data["is_direct_message"] = conversation.conversation_type == "private"

        if hasattr(message, "date"):
            self.message_data["timestamp"] = int(message.date.timestamp())
        else:
            self.message_data["timestamp"] = int(datetime.now().timestamp())

        edit_timestamp = None
        if hasattr(message, "edit_date") and message.edit_date:
            edit_timestamp = int(message.edit_date.timestamp())

        self.message_data["edit_timestamp"] = edit_timestamp
        self.message_data["edited"] = edit_timestamp is not None
        return self

    def with_content(self, event: Any) -> 'MessageBuilder':
        """Add message content"""
        if "updated_content" in event and event["updated_content"]:
            self.message_data["text"] = event["updated_content"]
        else:
            self.message_data["text"] = getattr(event["message"], "message", "")
        return self
