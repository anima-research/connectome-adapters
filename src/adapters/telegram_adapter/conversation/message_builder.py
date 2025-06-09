from datetime import datetime
from typing import Any, Optional

from src.core.conversation.base_data_classes import UserInfo
from src.core.conversation.base_message_builder import BaseMessageBuilder
from src.core.utils.config import Config

class MessageBuilder(BaseMessageBuilder):
    """Builds message objects from Telethon events"""

    def __init__(self, config: Config):
        self.config = config
        self.reset()

    def with_basic_info(self, message: Any, conversation: Any) -> 'MessageBuilder':
        """Add basic message info"""
        self.message_data["message_id"] = str(message.id)
        self.message_data["conversation_id"] = conversation.conversation_id
        self.message_data["is_direct_message"] = conversation.conversation_type == "private"

        if hasattr(message, 'date'):
            self.message_data["timestamp"] = int(message.date.timestamp())
        else:
            self.message_data["timestamp"] = int(datetime.now().timestamp())

        return self

    def with_sender_info(self, sender: Optional[UserInfo]) -> 'MessageBuilder':
        """Add sender information"""
        if sender:
            self.message_data["sender_id"] = sender.user_id
            self.message_data["sender_name"] = sender.display_name
            self.message_data["is_from_bot"] = (
                str(sender.user_id) == self.config.get_setting("adapter", "adapter_id")
            )
        else:
            self.message_data["is_from_bot"] = True

        return self

    def with_content(self, message: Any) -> 'MessageBuilder':
        """Add message content"""
        self.message_data["text"] = getattr(message, 'message', '')
        return self
