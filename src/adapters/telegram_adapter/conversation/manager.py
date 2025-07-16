import asyncio
import os
import re

from datetime import datetime
from enum import Enum
from typing import Dict, Optional, List, Any

from src.adapters.telegram_adapter.conversation.data_classes import ConversationInfo
from src.adapters.telegram_adapter.conversation.message_builder import MessageBuilder
from src.adapters.telegram_adapter.conversation.reaction_handler import ReactionHandler
from src.adapters.telegram_adapter.conversation.thread_handler import ThreadHandler

from src.core.conversation.base_data_classes import ConversationDelta, ThreadInfo
from src.core.conversation.base_manager import BaseManager
from src.core.conversation.base_message_builder import BaseMessageBuilder
from src.core.cache.message_cache import CachedMessage
from src.core.utils.config import Config

class TelegramEventType(str, Enum):
    """Types of events that can be processed"""
    NEW_MESSAGE = "new_message"
    EDITED_MESSAGE = "edited_message"
    DELETED_MESSAGE = "deleted_message"
    CHAT_ACTION = "chat_action"
    PINNED_MESSAGE = "pinned_message"
    UNPINNED_MESSAGE = "unpinned_message"

class Manager(BaseManager):
    """Tracks and manages information about Telegram conversations"""

    async def update_metadata(self, event: Any) -> List[Dict[str, Any]]:
        """Update the conversation metadata

        Args:
            event: Event object

        Returns:
            Dictionary with delta information
        """
        deltas = []
        platform_conversation_id = await self._get_platform_conversation_id(await self._get_peer(event))
        new_name = getattr(event.action, "title", None)

        for conversation in self.conversations.values():
            if self._update_conversation_metadata(conversation, platform_conversation_id, new_name):
                deltas.append(
                    ConversationDelta(
                        conversation_id=conversation.conversation_id,
                        conversation_name=conversation.conversation_name,
                        server_name=conversation.server_name
                    ).to_dict()
                )

        return deltas

    def _message_builder_class(self):
        """Message builder class"""
        return MessageBuilder

    def _thread_handler_class(self):
        """Thread handler class"""
        return ThreadHandler

    async def _get_or_create_conversation_info(self, event: Any) -> Optional[ConversationInfo]:
        """Get existing conversation info or create a new one

        Args:
            event: Event object

        Returns:
           Conversation info object or None if conversation can't be determined
        """
        peer = await self._get_peer(event["message"])

        platform_conversation_id = await self._get_platform_conversation_id(peer)
        if not platform_conversation_id:
            return None

        conversation_id = self._generate_deterministic_conversation_id(platform_conversation_id)
        if conversation_id in self.conversations:
            return self.conversations[conversation_id]

        self.conversations[conversation_id] = self._create_conversation_info(
            platform_conversation_id=platform_conversation_id,
            conversation_id=conversation_id,
            conversation_type=await self._get_conversation_type(peer)
        )

        return self.conversations[conversation_id]

    async def _get_peer(self, message: Any) -> Any:
        """Get the peer from a Telethon message

        Args:
            message: Telethon message object

        Returns:
            Peer object or None if not found
        """
        if not hasattr(message, "peer_id") and not hasattr(message, "peer"):
            return None
        return getattr(message, "peer_id", None) or getattr(message, "peer")

    async def _get_platform_conversation_id(self, peer: Any) -> Optional[str]:
        """Get the platform conversation ID from a Telethon message

        Args:
            peer: Telethon peer (user, chat or channel) object

        Returns:
            Conversation ID as string, or None if not found
        """
        if hasattr(peer, "user_id") and peer.user_id:
            return str(peer.user_id)
        if hasattr(peer, "chat_id") and peer.chat_id:
            return str(int(peer.chat_id) * -1)
        if hasattr(peer, "channel_id") and peer.channel_id:
            return f"-100{peer.channel_id}"

        return None

    async def _get_conversation_id_from_update(self, message: Any) -> Optional[str]:
        """Get the conversation ID from a message"""
        if isinstance(message, dict):
            return message.get("conversation_id", None)

        peer = await self._get_peer(message)
        platform_conversation_id = await self._get_platform_conversation_id(peer if peer else message)
        if not platform_conversation_id:
            return None

        return self._generate_deterministic_conversation_id(platform_conversation_id)

    async def _get_conversation_type(self, peer: Any) -> Optional[str]:
        """Get the conversation type from a Telethon peer
        Args:
            peer: Telethon peer (user, chat or channel) object

        Returns:
            Conversation type as string, or None if not found
        """
        if hasattr(peer, "user_id") and peer.user_id:
            return "private"
        if hasattr(peer, "chat_id") and peer.chat_id:
            return "group"
        if hasattr(peer, "channel_id") and peer.channel_id:
            return "channel"

        return None

    async def _update_conversation_name(self, event: Any, conversation_info: Any) -> None:
        """Update the conversation name

        Args:
            event: Event object
            conversation_info: Conversation info object

        Returns:
            Conversation name as string, or None if not found
        """
        if event.get("platform_conversation", None):
            if hasattr(event["platform_conversation"], "title"):
                conversation_info.conversation_name = getattr(event["platform_conversation"], "title", None)
                return

        conversation_info.conversation_name = self._get_custom_conversation_name(conversation_info)

    def _create_conversation_info(self,
                                  platform_conversation_id: str,
                                  conversation_id: str,
                                  conversation_type: str,
                                  server: Optional[str] = None) -> ConversationInfo:
        """Create a conversation info object

        Args:
            platform_conversation_id: Platform conversation ID
            conversation_id: Conversation ID
            conversation_type: Conversation type
            conversation_name: Conversation name
            server: Server object

        Returns:
            Conversation info object
        """
        return ConversationInfo(
            platform_conversation_id=platform_conversation_id,
            conversation_id=conversation_id,
            conversation_type=conversation_type,
            server_id=None,
            server_name=None,
            just_started=True
        )

    async def _process_event(self,
                             event: Dict[str, Any],
                             conversation_info: ConversationInfo,
                             delta: ConversationDelta) -> None:
        """Process an event based on event type

        Args:
            event: Event object that should contain the following keys:
                - event_type: Type of event
                - message: Telethon message object
            conversation_info: Conversation info object
            delta: Delta object to update
        """
        event_type = event.get("event_type", None)
        message = event.get("message", None)

        if event_type == TelegramEventType.EDITED_MESSAGE:
            cached_msg = await self._update_message(event, conversation_info, delta)
            if cached_msg:
                await self._update_delta_list(
                    conversation_id=conversation_info.conversation_id,
                    delta=delta,
                    list_to_update="updated_messages",
                    cached_msg=cached_msg,
                    mentions=event.get("mentions", [])
                )
            return

        if event_type == TelegramEventType.PINNED_MESSAGE:
            cached_msg = await self._pin_message(message, conversation_info)
            if cached_msg:
                delta.pinned_message_ids.append(cached_msg.message_id)
            return

        if event_type == TelegramEventType.UNPINNED_MESSAGE:
            cached_msg = await self._unpin_message(message, conversation_info)
            if cached_msg:
                delta.unpinned_message_ids.append(cached_msg.message_id)

    async def _create_message(self,
                              event: Any,
                              conversation_info: ConversationInfo,
                              thread_info: ThreadInfo) -> CachedMessage:
        """Create a new message in the cache

        Args:
            event: Event object
            conversation_info: Conversation info object
            thread_info: Thread info object

        Returns:
            Cached message object
        """
        cached_msg = await super()._create_message(event, conversation_info, thread_info)
        cached_msg.reactions = await ReactionHandler.extract_reactions(event["message"].reactions)
        return cached_msg

    async def _update_message(self,
                              event: Any,
                              conversation_info: ConversationInfo,
                              delta: ConversationDelta) -> Optional[CachedMessage]:
        """Process a message based on event type

        Args:
            event: Event object
            conversation_info: Conversation info object
            delta: Delta object to update

        Returns:
            Cached message object or None if message not found
        """
        cached_msg = await self.cache.message_cache.get_message_by_id(
            conversation_id=conversation_info.conversation_id,
            message_id=str(getattr(event["message"], "id", ""))
        )

        if not cached_msg:
            return None

        if "updated_content" in event and event["updated_content"]:
            updated_text = event["updated_content"]
        else:
            updated_text = getattr(event["message"], "message", None)

        if updated_text is not None and updated_text != cached_msg.text:
            cached_msg.text = updated_text
            edit_date = getattr(event["message"], "edit_date", None)
            cached_msg.edit_timestamp = int((edit_date if edit_date else datetime.now()).timestamp())
            cached_msg.edited = True
        elif updated_text == cached_msg.text:
            delta.message_id = cached_msg.message_id
            ReactionHandler.update_message_reactions(
                cached_msg,
                await ReactionHandler.extract_reactions(event["message"].reactions),
                delta
            )

        return cached_msg

    async def _pin_message(self,
                           message: Any,
                           conversation_info: ConversationInfo) -> None:
        """Process a pinned message event

        Args:
            message: Telethon message object
            conversation_info: Conversation info object
        """
        message_id = None
        timestamp = int(datetime.now().timestamp())

        if hasattr(message, "reply_to") and message.reply_to:
            message_id = str(message.reply_to.reply_to_msg_id)
            timestamp = int(getattr(message, "date", datetime.now()).timestamp())
        elif isinstance(message, dict):
            message_id = message.get("message_id", None)

        if message_id:
            return await self._update_pin_status(
                message_id, conversation_info, True, timestamp
            )

        return None

    async def _unpin_message(self,
                             message: Any,
                             conversation_info: ConversationInfo) -> None:
        """Process an unpinned message event

        Args:
            message: Telethon message object
            conversation_info: Conversation info object
        """
        message_id = None
        if hasattr(message, "messages") and message.messages:
            message_id = str(message.messages[0])
        elif isinstance(message, dict):
            message_id = message.get("message_id", None)

        if message_id:
            return await self._update_pin_status(
                message_id,
                conversation_info,
                False,
                int(datetime.now().timestamp())
            )

        return None

    async def _update_pin_status(self,
                                 message_id: str,
                                 conversation_info: ConversationInfo,
                                 is_pinned: bool,
                                 timestamp: int) -> Optional[CachedMessage]:
        """Update the pin status of a message

        Args:
            message_id: ID of the message
            conversation_info: Conversation info object
            is_pinned: Whether the message is pinned
            timestamp: Timestamp of the message pin status update

        Returns:
            Cached message object or None if message not found
        """
        cached_msg = await self.cache.message_cache.get_message_by_id(
            conversation_id=conversation_info.conversation_id,
            message_id=message_id
        )

        if not cached_msg:
            return None

        cached_msg.is_pinned = is_pinned
        cached_msg.timestamp = timestamp

        if is_pinned:
            conversation_info.pinned_messages.add(message_id)
        else:
            conversation_info.pinned_messages.discard(message_id)

        return cached_msg

    async def _get_deleted_message_ids(self, event: Dict[str, Any]) -> List[str]:
        """Get the deleted message IDs from an event

        Args:
            event: Event object

        Returns:
            List of deleted message IDs
        """
        deleted_ids = event.get("deleted_ids", []) or getattr(event["event"], "deleted_ids", [])

        return [str(msg_id) for msg_id in deleted_ids]

    async def _get_conversation_info_to_delete_from(self,
                                                    event: Any,
                                                    deleted_ids: List[str] = []) -> Optional[ConversationInfo]:
        """Get the conversation info to delete from

        Args:
            event: Event object
            deleted_ids: List of deleted message IDs

        Returns:
            Conversation info object or None if conversation not found
        """
        platform_conversation_id = (
            event.get("conversation_id", None) or
            await self._get_platform_conversation_id(event["event"])
        )
        if not platform_conversation_id:
            return None

        conversation_id = self._generate_deterministic_conversation_id(platform_conversation_id)
        if conversation_id in self.conversations:
            return self.conversations[conversation_id]

        best_match = None
        best_match_count = 0

        for id, messages in self.cache.message_cache.messages.items():
            matching_ids = set(deleted_ids).intersection(set(messages.keys()))
            if not matching_ids:
                continue

            match_count = len(matching_ids)
            if match_count > best_match_count:
                best_match = self.conversations[id]
                best_match_count = match_count

        return best_match
