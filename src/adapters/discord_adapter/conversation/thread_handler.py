import re
from typing import Any, Optional, Tuple

from src.core.conversation.base_data_classes import ThreadInfo
from src.core.conversation.base_thread_handler import BaseThreadHandler

class ThreadHandler(BaseThreadHandler):
    """Handles thread information for Discord messages"""

    def _add_message_to_thread_info(self, thread_info: ThreadInfo, message: Any) -> None:
        """Add a message to a thread info

        Args:
            thread_info: Thread info object
            message: Message object
        """
        message_id = str(getattr(message, "id", ""))

        if message_id:
            thread_info.messages.add(message_id)

    def _extract_reply_to_id(self, message: Any) -> Optional[str]:
        """Extract the reply_to_message_id from a message.

        Args:
            message: Discord message object

        Returns:
            Message ID being replied to, or None if not a reply
        """
        if not message or not hasattr(message, "reference") or not message.reference:
            return None

        return str(message.reference.message_id)
