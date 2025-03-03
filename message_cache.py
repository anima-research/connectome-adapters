import asyncio
import logging

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Union, Set, Any

from config import Config

@dataclass
class CachedMessage:
    message_id: str
    conversation_id: str
    thread_id: Optional[str]
    sender_id: str
    sender_name: str
    text: Optional[str]
    timestamp: datetime
    is_from_bot: bool
    reply_to_message_id: Optional[str] = None
    media_info: Optional[Dict] = None
    raw_data: Optional[Dict] = None  # Original message data for reference

    @property
    def age_seconds(self) -> float:
        """Get message age in seconds"""
        return (datetime.now() - self.timestamp).total_seconds()

"""
Message caching system with privacy and security features.

Security notes for future persistent implementation:
1. When implementing database storage, add encryption for stored messages
2. Implement proper access control based on user identity
3. Use secure deletion practices appropriate for the storage medium
4. Consider adding audit logging for sensitive operations
"""
class MessageCache:
    def __init__(self):
        self.config = Config().get_instance()
        self.messages: Dict[str, Dict[str, CachedMessage]] = {}  # conversation_id -> message_id -> message
        self.max_messages_per_conversation = self.config.get_setting("max_messages_per_conversation")
        self.max_total_messages = self.config.get_setting("max_total_messages")
        self.max_age_seconds = self.config.get_setting("max_age_hours") * 3600
        self._lock = asyncio.Lock()
        self.maintenance_task = asyncio.create_task(self._maintenance_loop())
        self.retention_direct = int(self.config.get_setting("privacy.retention_direct_messages")) * 86400  # days to seconds
        self.retention_group = int(self.config.get_setting("privacy.retention_group_messages")) * 86400  # days to seconds

    def __del__(self):
        """Cleanup when object is garbage collected"""
        if self.maintenance_task:
            if not self.maintenance_task.done() and not self.maintenance_task.cancelled():
                self.maintenance_task.cancel()
                logging.info("Cache maintenance task cancelled during cleanup")

    async def add_message(self, message: CachedMessage) -> None:
        """Add a message to the cache"""
        async with self._lock:
            if message.conversation_id not in self.messages:
                self.messages[message.conversation_id] = {}

            self.messages[message.conversation_id][message.message_id] = message
            logging.debug(f"Added message {message.message_id} to cache for conversation {message.conversation_id}")

    async def _enforce_conversation_limit(self, conversation_id: str) -> None:
        """Ensure conversation doesn't exceed message limit"""
        conversation = self.messages[conversation_id]
        if len(conversation) <= self.max_messages_per_conversation:
            return

        # Sort by timestamp and remove oldest
        sorted_messages = sorted(
            conversation.values(),
            key=lambda m: m.timestamp
        )

        # Keep only the newest messages
        to_keep = sorted_messages[-self.max_messages_per_conversation:]

        # Rebuild conversation dict with only kept messages
        self.messages[conversation_id] = {
            msg.message_id: msg for msg in to_keep
        }

    async def _enforce_total_limit(self) -> None:
        """Ensure total messages don't exceed limit"""
        total_count = sum(len(msgs) for msgs in self.messages.values())
        if total_count <= self.max_total_messages:
            return

        # Count how many to remove
        to_remove = total_count - self.max_total_messages

        # Flatten all messages and sort by age
        all_messages = []
        for conv_id, messages in self.messages.items():
            for msg_id, msg in messages.items():
                all_messages.append((conv_id, msg_id, msg.timestamp))

        # Sort by timestamp (oldest first)
        all_messages.sort(key=lambda x: x[2])

        # Remove oldest messages
        for i in range(to_remove):
            if i >= len(all_messages):
                break
            conv_id, msg_id, _ = all_messages[i]
            if conv_id in self.messages and msg_id in self.messages[conv_id]:
                del self.messages[conv_id][msg_id]

        # Clean up empty conversations
        empty_convs = [
            conv_id for conv_id, msgs in self.messages.items()
            if not msgs
        ]
        for conv_id in empty_convs:
            del self.messages[conv_id]

    async def get_messages(self,
                          conversation_id: str,
                          limit: int = 50,
                          thread_id: Optional[str] = None,
                          before_timestamp: Optional[datetime] = None,
                          after_timestamp: Optional[datetime] = None,
                          sender_id: Optional[str] = None,
                          include_bot_messages: bool = True,
                          newest_first: bool = True) -> List[CachedMessage]:
        """Get messages with flexible filtering"""
        async with self._lock:
            if conversation_id not in self.messages:
                return []

            # Get all messages for this conversation
            messages = list(self.messages[conversation_id].values())

            # Apply filters
            if thread_id:
                messages = [m for m in messages if m.thread_id == thread_id]

            if before_timestamp:
                messages = [m for m in messages if m.timestamp < before_timestamp]

            if after_timestamp:
                messages = [m for m in messages if m.timestamp > after_timestamp]

            if sender_id:
                messages = [m for m in messages if m.sender_id == sender_id]

            if not include_bot_messages:
                messages = [m for m in messages if not m.is_from_bot]

            # Sort by timestamp
            messages.sort(key=lambda m: m.timestamp, reverse=newest_first)

            # Apply limit
            return messages[:limit]

    async def get_message_by_id(self, conversation_id: str, message_id: str) -> Optional[CachedMessage]:
        """Get a specific message by ID"""
        async with self._lock:
            if conversation_id in self.messages and message_id in self.messages[conversation_id]:
                return self.messages[conversation_id][message_id]
            return None

    async def get_thread_messages(self, conversation_id: str, thread_id: str,
                                 limit: int = 50, newest_first: bool = True) -> List[CachedMessage]:
        """Get all messages in a specific thread"""
        return await self.get_messages(
            conversation_id=conversation_id,
            thread_id=thread_id,
            limit=limit,
            newest_first=newest_first
        )

    async def get_message_history(self, conversation_id: str, limit: int = 50) -> List[CachedMessage]:
        """Standard method for retrieving message history"""
        async with self._lock:
            if conversation_id not in self.messages:
                return []

            messages = list(self.messages[conversation_id].values())
            messages.sort(key=lambda m: m.timestamp, reverse=True)

            return messages[:limit]

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the cache"""
        total_messages = sum(len(msgs) for msgs in self.messages.values())
        conversations = len(self.messages)

        # Calculate age statistics
        ages = []
        for conv_messages in self.messages.values():
            for msg in conv_messages.values():
                ages.append(msg.age_seconds)

        avg_age = sum(ages) / len(ages) if ages else 0
        oldest = max(ages) if ages else 0
        newest = min(ages) if ages else 0

        return {
            "total_messages": total_messages,
            "conversations": conversations,
            "average_message_age_seconds": avg_age,
            "oldest_message_seconds": oldest,
            "newest_message_seconds": newest,
            "cache_limit_per_conversation": self.max_messages_per_conversation,
            "cache_limit_total": self.max_total_messages
        }

    async def _maintenance_loop(self):
        """Periodically clean up old messages"""
        try:
            while True:
                await asyncio.sleep(int(self.config.get_setting("cache_maintenance_interval")))
                removed = await self._clear_old_messages()
                if removed > 0:
                    logging.info(f"Cache maintenance: removed {removed} old messages")
        except Exception as e:
            logging.error(f"Error in cache maintenance: {e}")

    async def _clear_old_messages(self) -> int:
        """Clear messages based on retention policy, returns count of removed messages"""
        async with self._lock:
            now = datetime.now()
            removed_count = 0
            empty_convs = []

            for conv_id, messages in self.messages.items():
                is_private = not (conv_id.startswith('-') or conv_id.startswith('channel'))
                max_age = self.retention_direct if is_private else self.retention_group
                cutoff = now - timedelta(seconds=max_age)

                to_remove = [
                    msg_id for msg_id, msg in messages.items()
                    if msg.timestamp < cutoff
                ]

                for msg_id in to_remove:
                    del messages[msg_id]
                    removed_count += 1

                if not messages:
                    empty_convs.append(conv_id)

            for conv_id in empty_convs:
                del self.messages[conv_id]

            return removed_count

    async def delete_user_data(self, user_id: str) -> int:
        """Delete all data for a specific user from the cache (driver method)

        Args:
            user_id: The user ID whose data should be deleted

        Returns:
            int: Number of messages deleted
        """
        async with self._lock:
            deleted_count = 0
            conversations_to_check = list(self.messages.keys())

            for conversation_id in conversations_to_check:
                if conversation_id not in self.messages:
                    continue

                # Determine if this is a private conversation
                if str(conversation_id) == str(user_id):
                    deleted = await self._delete_private_chat_data(conversation_id)
                else:
                    deleted = await self._delete_group_chat_data(conversation_id, user_id)

                deleted_count += deleted

                if conversation_id in self.messages and not self.messages[conversation_id]:
                    del self.messages[conversation_id]

            logging.info(f"Deleted {deleted_count} messages related to user {user_id}")
            return deleted_count

    async def _delete_private_chat_data(self, conversation_id: str) -> int:
        """Delete all data in a private chat

        Args:
            conversation_id: The conversation ID (same as user ID for private chats)

        Returns:
            int: Number of messages deleted
        """
        if conversation_id not in self.messages:
            return 0

        messages = self.messages[conversation_id]
        message_count = len(messages)
        messages.clear()

        return message_count

    async def _delete_group_chat_data(self, conversation_id: str, user_id: str) -> int:
        """Delete user data in a group chat

        Args:
            conversation_id: The conversation ID
            user_id: The user ID whose data should be deleted

        Returns:
            int: Number of messages deleted
        """
        if conversation_id not in self.messages:
            return 0

        deleted_count = 0
        messages = self.messages[conversation_id]

        # Step 1: Find messages by this user
        user_message_ids = [
            msg_id for msg_id, msg in messages.items()
            if msg.sender_id == user_id
        ]

        # Step 2: Find bot responses to this user's messages
        response_message_ids = []
        for msg_id, msg in messages.items():
            if msg.is_from_bot and msg.reply_to_message_id:
                if msg.reply_to_message_id in user_message_ids:
                    response_message_ids.append(msg_id)

        # Step 3: Delete both user messages and bot responses
        all_ids_to_delete = user_message_ids + response_message_ids

        for msg_id in all_ids_to_delete:
            if msg_id in messages:
                del messages[msg_id]
                deleted_count += 1

        logging.info(f"Deleted {deleted_count} messages in group chat {conversation_id}")
        return deleted_count