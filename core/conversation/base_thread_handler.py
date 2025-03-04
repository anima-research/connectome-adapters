import logging

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional

from core.cache.message_cache import MessageCache, CachedMessage
from core.conversation.base_data_classes import BaseConversationInfo, ThreadInfo

class BaseThreadHandler(ABC):
    """Handles thread information for messages

    Thread hierarchy:
    - A thread is identified by a thread_id (usually the ID of the root message)
    - Messages can have a reply_to_message_id pointing to their parent
    - The root_message_id is the ultimate ancestor in the thread
    """

    def __init__(self, message_cache: MessageCache):
        self.message_cache = message_cache

    async def add_thread_info(self,
                              message: Any,
                              conversation_info: BaseConversationInfo) -> Optional[ThreadInfo]:
        """Add thread info to a conversation info

        Args:
            message: Message object
            conversation_info: Conversation info object

        Returns:
            Thread info object if found, None otherwise
        """
        reply_to_msg_id = self._extract_reply_to_id(message)

        if not reply_to_msg_id:
            return None

        thread_id = reply_to_msg_id
        thread_info = None

        if thread_id in conversation_info.threads:
            thread_info = conversation_info.threads[thread_id]
        else:
            root_message_id = reply_to_msg_id

            try:
                replied_msg = await self.message_cache.get_message_by_id(
                    conversation_id=conversation_info.conversation_id,
                    message_id=reply_to_msg_id
                )
                if replied_msg and replied_msg.reply_to_message_id:
                    parent_thread_id = replied_msg.thread_id or replied_msg.reply_to_message_id
                    if parent_thread_id in conversation_info.threads:
                        root_message_id = conversation_info.threads[parent_thread_id].root_message_id
            except Exception as e:
                logging.warning(f"Error finding thread root: {e}")

            thread_info = ThreadInfo(thread_id=thread_id, root_message_id=root_message_id)

        self._add_message_to_thread_info(thread_info, message)
        thread_info.last_activity = datetime.now()
        conversation_info.threads[thread_id] = thread_info

        return thread_info

    def remove_thread_info(self,
                           conversation_info: BaseConversationInfo,
                           cached_message: CachedMessage) -> None:
        """Remove thread info from a message

        Args:
            conversation_info: Conversation info object
            thread_id: Thread ID
        """
        if cached_message.thread_id in conversation_info.threads:
            thread_info = conversation_info.threads[cached_message.thread_id]
            thread_info.messages.discard(cached_message.message_id)

            if len(thread_info.messages) == 0:
                del conversation_info.threads[cached_message.thread_id]

    @abstractmethod
    def _add_message_to_thread_info(self, thread_info: ThreadInfo, message: Any) -> None:
        """Add a message to a thread info"""
        raise NotImplementedError("Child classes must implement _add_message_to_thread_info")

    @abstractmethod
    def _extract_reply_to_id(self, message: Any) -> Optional[str]:
        """Extract the reply_to_message_id from a message"""
        raise NotImplementedError("Child classes must implement _extract_reply_to_id")
