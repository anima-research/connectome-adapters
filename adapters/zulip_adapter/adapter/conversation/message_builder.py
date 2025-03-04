from typing import Dict, Any, Optional
from datetime import datetime

from core.conversation.base_data_classes import UserInfo, ThreadInfo

class MessageBuilder:
    """Builds message objects from Telethon events"""

    def __init__(self):
        self.reset()

    def reset(self):
        """Reset the builder to its initial state"""
        self.message_data = {}
        return self

    def with_basic_info(self, message: Dict[str, Any], conversation_id: str) -> 'MessageBuilder':
        """Add basic message info"""
        self.message_data["message_id"] = str(message["id"]) if message.get("id", None) else None
        self.message_data["conversation_id"] = conversation_id
        self.message_data["timestamp"] = message.get("timestamp", None)

        return self

    def with_sender_info(self, sender: Optional[UserInfo]) -> 'MessageBuilder':
        """Add sender information"""
        if sender:
            self.message_data["sender_id"] = sender.user_id
            self.message_data["sender_name"] = sender.display_name
            self.message_data["is_from_bot"] = sender.is_bot

        return self

    def with_content(self, message: Any) -> 'MessageBuilder':
        """Add message content"""
        self.message_data["text"] = message.get("content", None)

        return self

    def with_thread_info(self, thread_info: ThreadInfo) -> 'MessageBuilder':
        """Add thread information"""
        if thread_info:
            self.message_data["thread_id"] = thread_info.thread_id
            self.message_data["reply_to_message_id"] = thread_info.thread_id

        return self

    def build(self) -> Dict[str, Any]:
        """Build the final message object"""
        return self.message_data.copy()
