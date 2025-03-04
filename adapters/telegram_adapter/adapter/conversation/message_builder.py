from datetime import datetime
from typing import Dict, Any, Optional

from core.conversation.base_data_classes import ThreadInfo, UserInfo
from core.utils.config import Config

class MessageBuilder:
    """Builds message objects from Telethon events"""

    def __init__(self, config: Config):
        self.config = config
        self.reset()

    def reset(self):
        """Reset the builder to its initial state"""
        self.message_data = {}
        return self

    def with_basic_info(self, message: Any, conversation_id: str) -> 'MessageBuilder':
        """Add basic message info"""
        self.message_data["message_id"] = str(message.id)
        self.message_data["conversation_id"] = conversation_id

        if hasattr(message, 'date'):
            self.message_data["timestamp"] = int(message.date.timestamp() * 1e3)
        else:
            self.message_data["timestamp"] = int(datetime.now().timestamp() * 1e3)

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

    def with_thread_info(self, thread_info: ThreadInfo) -> 'MessageBuilder':
        """Add thread information"""
        if thread_info:
            self.message_data["thread_id"] = thread_info.thread_id
            self.message_data["reply_to_message_id"] = thread_info.thread_id

        return self

    def with_content(self, message: Any) -> 'MessageBuilder':
        """Add message content"""
        self.message_data["text"] = getattr(message, 'message', '')
        return self

    def build(self) -> Dict[str, Any]:
        """Build the final message object"""
        return self.message_data.copy()
