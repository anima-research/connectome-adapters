import re
from typing import Any, Optional, Tuple

from adapters.zulip_adapter.adapter.conversation.data_classes import ConversationInfo

from core.cache.message_cache import MessageCache
from core.conversation.base_data_classes import ThreadInfo
from core.conversation.base_thread_handler import BaseThreadHandler

class ThreadHandler(BaseThreadHandler):
    """Handles thread information for Zulip messages"""

    def __init__(self, message_cache: MessageCache):
        super().__init__(message_cache)

    async def update_thread_info(self,
                                 message: Any,
                                 conversation_info: ConversationInfo) -> Tuple[bool, Optional[ThreadInfo]]:
        """Update thread info when a message is edited

        Args:
            message: Edited message object
            conversation_info: Conversation info object

        Returns:
            Tuple of (bool indicating if threading changed, updated ThreadInfo)
        """
        new_reply_to_id = self._extract_reply_to_id(message)
        old_reply_to_id = self._extract_reply_to_id({"content": message.get("orig_content", "")})

        # Case 1: No change in thread reference
        if old_reply_to_id == new_reply_to_id:
            return (False, None)

        # Case 2: Reply reference was removed
        if old_reply_to_id and not new_reply_to_id:
            return (True, None)

        # Case 3: Reply reference was added or changed
        if new_reply_to_id:
            thread_info = await self.add_thread_info(message, conversation_info)
            return (True, thread_info)

        return (False, None)

    def _add_message_to_thread_info(self, thread_info: ThreadInfo, message: Any) -> None:
        """Add a message to a thread info

        Args:
            thread_info: Thread info object
            message: Message object
        """
        message_id = str(message["id"]) if message.get("id", None) else None
        if message_id:
            thread_info.messages.add(message_id)

    def _extract_reply_to_id(self, message: Any) -> Optional[str]:
        """Extract the reply_to_message_id from a message.
        We look for the pattern: [said](https://zulip.at-hub.com/#narrow/.../near/MESSAGE_ID).

        Args:
            message: Message object

        Returns:
            Message ID being replied to, or None if not a reply
        """
        if not message or "content" not in message:
            return None

        pattern = r'\[said\]\([^\)]+/near/(\d+)\)'
        match = re.search(pattern, message.get("content", ""))

        if match:
            return match.group(1)

        return None
