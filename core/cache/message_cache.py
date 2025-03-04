import asyncio
import logging

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from core.utils.config import Config

@dataclass
class CachedMessage:
    message_id: str
    conversation_id: str
    thread_id: Optional[str]
    sender_id: str
    sender_name: str
    text: Optional[str]
    timestamp: Optional[int]
    is_from_bot: bool
    reply_to_message_id: Optional[str] = None
    reactions: Dict[str, int] = field(default_factory=dict)
    is_pinned: bool = False
    attachments: Set[str] = field(default_factory=set)

    @property
    def age_seconds(self) -> float:
        """Get message age in seconds"""
        return (datetime.now() - datetime.fromtimestamp(self.timestamp / 1e3)).total_seconds()

    def cache_to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "message_id": self.message_id,
            "conversation_id": self.conversation_id,
            "thread_id": self.thread_id,
            "sender": {
                "user_id": self.sender_id,
                "display_name": self.sender_name
            },
            "text": self.text,
            "timestamp": self.timestamp
        }

class MessageCache:
    """Tracks and manages message history"""

    def __init__(self, config: Config, start_maintenance=False):
        """Initialize the MessageCache

        Args:
            config: Config instance
            start_maintenance: Whether to start the maintenance loop
        """
        self.config = config
        self.messages: Dict[str, Dict[str, CachedMessage]] = {}  # conversation_id -> message_id -> message
        self.max_messages_per_conversation = self.config.get_setting("caching", "max_messages_per_conversation")
        self.max_total_messages = self.config.get_setting("caching", "max_total_messages")
        self.max_age_seconds = self.config.get_setting("caching", "max_age_hours") * 3600
        self._lock = asyncio.Lock()
        self.maintenance_task = asyncio.create_task(self._maintenance_loop()) if start_maintenance else None

    def __del__(self):
        """Cleanup when object is garbage collected"""
        if self.maintenance_task:
            if not self.maintenance_task.done() and not self.maintenance_task.cancelled():
                self.maintenance_task.cancel()
                logging.info("Cache maintenance task cancelled during cleanup")

    def get_messages_by_conversation_id(self, conversation_id: str) -> List[str]:
        """Get all messages for a given conversation ID

        Args:
            conversation_id: Conversation ID

        Returns:
            Dictionary of message IDs to CachedMessage objects
        """
        return list(self.messages.get(conversation_id, {}).keys())

    async def get_message_by_id(self, conversation_id: str, message_id: str) -> Optional[CachedMessage]:
        """Get a specific message by ID

        Args:
            conversation_id: Conversation ID
            message_id: Message ID

        Returns:
            CachedMessage object or None if not found
        """
        async with self._lock:
            if conversation_id in self.messages and message_id in self.messages[conversation_id]:
                return self.messages[conversation_id][message_id]
            return None

    async def add_message(self, message_info: Dict[str, Any]) -> None:
        """Add a message to the cache

        Args:
            message_info: Message info dictionary

        Returns:
            CachedMessage object
        """
        cached_message = await self.get_message_by_id(
            message_info["conversation_id"], message_info["message_id"]
        )

        if cached_message:
            return cached_message

        async with self._lock:
            if message_info["conversation_id"] not in self.messages:
                self.messages[message_info["conversation_id"]] = {}

            self.messages[message_info["conversation_id"]][message_info["message_id"]] = CachedMessage(
                message_id=message_info["message_id"],
                conversation_id=message_info["conversation_id"],
                thread_id=message_info.get("thread_id", None),
                sender_id=message_info.get("sender_id", None),
                sender_name=message_info.get("sender_name", None),
                text=message_info["text"],
                timestamp=message_info["timestamp"],
                is_from_bot=message_info.get("is_from_bot", True),
                reply_to_message_id=message_info.get("reply_to_message_id", None)
            )

            return self.messages[message_info["conversation_id"]][message_info["message_id"]]

    async def migrate_message(self,
                              old_conversation_id: str,
                              new_conversation_id: str,
                              message_id: str) -> None:
        """Handle migration of messages when a group becomes a supergroup

        Args:
            old_conversation_id: Old conversation ID
            new_conversation_id: New conversation ID
            message_id: Message ID
        """
        async with self._lock:
            if old_conversation_id not in self.messages or message_id not in self.messages[old_conversation_id]:
                return

            if new_conversation_id not in self.messages:
                self.messages[new_conversation_id] = {}

            self.messages[new_conversation_id][message_id] = self.messages[old_conversation_id][message_id]
            self.messages[new_conversation_id][message_id].conversation_id = new_conversation_id

            del self.messages[old_conversation_id][message_id]

    async def delete_message(self, conversation_id: str, message_id: str) -> bool:
        """Delete a message from the cache

        Args:
            conversation_id: ID of the conversation containing the message
            message_id: ID of the message to delete

        Returns:
            bool: True if message was deleted, False if not found
        """
        async with self._lock:
            if conversation_id not in self.messages or message_id not in self.messages[conversation_id]:
                return False
            del self.messages[conversation_id][message_id]
            return True

    async def _maintenance_loop(self):
        """Periodically perform cache maintenance"""
        try:
            while True:
                await asyncio.sleep(int(self.config.get_setting("caching", "cache_maintenance_interval")))
                async with self._lock:
                    for conv_id in list(self.messages.keys()):
                        if conv_id in self.messages:  # Check again in case it was removed
                            if not self.messages[conv_id]:
                                del self.messages[conv_id]
                            await self._enforce_conversation_limit(conv_id)
                    await self._enforce_total_limit()
                logging.debug(f"Cache maintenance completed. Current size: {sum(len(msgs) for msgs in self.messages.values())} messages")
        except Exception as e:
            logging.error(f"Error in cache maintenance: {e}")

    async def _enforce_conversation_limit(self, conversation_id: str) -> None:
        """Ensure conversation doesn't exceed message limit

        Args:
            conversation_id: Conversation ID
        """
        conversation = self.messages[conversation_id]
        if len(conversation) <= self.max_messages_per_conversation:
            return

        sorted_messages = sorted(
            conversation.values(),
            key=lambda m: datetime.fromtimestamp(m.timestamp / 1e3)
        )
        self.messages[conversation_id] = {
            msg.message_id: msg for msg in sorted_messages[-self.max_messages_per_conversation:]
        }

    async def _enforce_total_limit(self) -> None:
        """Ensure total messages don't exceed limit"""
        total_count = sum(len(msgs) for msgs in self.messages.values())
        if total_count <= self.max_total_messages:
            return

        to_remove = total_count - self.max_total_messages

        all_messages = []
        for conv_id, messages in self.messages.items():
            for msg_id, msg in messages.items():
                all_messages.append(
                    (conv_id, msg_id, datetime.fromtimestamp(msg.timestamp / 1e3))
                )

        all_messages.sort(key=lambda x: x[2])

        for i in range(to_remove):
            if i >= len(all_messages):
                break
            conv_id, msg_id, _ = all_messages[i]
            if conv_id in self.messages and msg_id in self.messages[conv_id]:
                del self.messages[conv_id][msg_id]

        empty_convs = [
            conv_id for conv_id, msgs in self.messages.items()
            if not msgs
        ]
        for conv_id in empty_convs:
            del self.messages[conv_id]
