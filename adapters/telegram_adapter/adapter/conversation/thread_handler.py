from typing import Any, Optional

from core.cache.message_cache import MessageCache
from core.conversation.base_data_classes import ThreadInfo
from core.conversation.base_thread_handler import BaseThreadHandler

class ThreadHandler(BaseThreadHandler):
    """Handles thread information"""

    def __init__(self, message_cache: MessageCache):
        super().__init__(message_cache)

    def _add_message_to_thread_info(self, thread_info: ThreadInfo, message: Any) -> None:
        """Add a message to a thread info

        Args:
            thread_info: Thread info object
            message: Message object
        """
        message_id = getattr(message, "id", None)

        if message_id:
            thread_info.messages.add(message_id)
    def _extract_reply_to_id(self, message: Any) -> Optional[str]:
        """Extract the reply_to_message_id from a message.

        Args:
            message: Telethon message object

        Returns:
            Message ID being replied to, or None if not a reply
        """
        if not message or not hasattr(message, "reply_to") or not message.reply_to:
            return None

        return str(message.reply_to.reply_to_msg_id)
