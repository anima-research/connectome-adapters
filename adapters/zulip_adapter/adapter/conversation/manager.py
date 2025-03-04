import asyncio

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from adapters.zulip_adapter.adapter.conversation.data_classes import ConversationInfo
from adapters.zulip_adapter.adapter.conversation.message_builder import MessageBuilder
from adapters.zulip_adapter.adapter.conversation.reaction_handler import ReactionHandler
from adapters.zulip_adapter.adapter.conversation.thread_handler import ThreadHandler
from adapters.zulip_adapter.adapter.conversation.user_builder import UserBuilder

from core.conversation.base_data_classes import ConversationDelta, ThreadInfo, UserInfo
from core.conversation.base_manager import BaseManager
from core.cache.message_cache import CachedMessage
from core.utils.config import Config

class ZulipEventType(str, Enum):
    """Types of events that can be processed"""
    MESSAGE = "message"
    UPDATE_MESSAGE = "update_message"
    REACTION = "reaction"

class Manager(BaseManager):
    """Tracks and manages information about Zulip conversations"""

    def __init__(self, config: Config, start_maintenance=False):
        """Initialize the conversation manager

        Args:
            config: Config instance
            start_maintenance: Whether to start the maintenance loop
        """
        super().__init__(config, start_maintenance)
        self.message_builder = MessageBuilder()
        self.thread_handler = ThreadHandler(self.message_cache)

    async def migrate_between_conversations(self, event: Any) -> Dict[str, Any]:
        """Handle a supergroup that was migrated from a regular group

        Args:
            event: Zulip event object

        Returns:
            Dictionary with delta information
        """
        event.update({"type": "stream"})

        return await super().migrate_between_conversations(event)

    async def _get_conversation_id(self, message: Any) -> Optional[str]:
        """Get the conversation ID from a Zulip message

        Args:
            message: Zulip message object

        Returns:
            Conversation ID as string, or None if not found
        """
        if message.get("type", None) == "private":
            return self._get_private_conversation_id(message)
        if message.get("type", None) == "stream" and message.get("stream_id", None):
            return self._get_stream_conversation_id(message)

        return None

    def _get_private_conversation_id(self, message: Dict[str, Any]) -> str:
        """Create a conversation ID for a private message

        Args:
            message: Zulip message object

        Returns:
            Conversation ID as a comma-separated list of user IDs
        """
        user_ids = sorted(
            [str(p.get("id")) for p in message.get("display_recipient", []) if "id" in p]
        )
        return "_".join(user_ids)

    def _get_stream_conversation_id(self, message: Dict[str, Any]) -> str:
        """Create a conversation ID for a stream message

        Args:
            message: Zulip message object

        Returns:
            Conversation ID as a slash-separated combination of stream id and topic
        """
        stream_id = str(message.get("stream_id", ""))
        topic = message.get("subject", "")
        return f"{stream_id}/{topic}" if stream_id and topic else ""

    async def _get_conversation_id_from_update(self, message: Any) -> Optional[str]:
        """Get the conversation ID from a Zulip message

        Args:
            message: Zulip message object

        Returns:
            Conversation ID as string, or None if not found
        """
        message_id = str(message.get("message_id", ""))

        if message_id:
            for conversation_id, conversation_info in self.conversations.items():
                if message_id in conversation_info.messages:
                    return conversation_id

        return None

    async def _get_conversation_type(self, message: Any) -> Optional[str]:
        """Get the conversation type from a message

        Args:
            message: Zulip message object

        Returns:
            Conversation type as string, or None if not found
        """
        return message.get("type", None)

    async def _get_conversation_name(self, message: Any) -> Optional[str]:
        """Get the conversation name from a message

        Args:
            message: Zulip message object

        Returns:
            Conversation name as string, or None if not found
        """
        if message.get("type", None) == "stream":
            return message.get("display_recipient", None)
        return None

    def _create_conversation_info(self,
                                  conversation_id: str,
                                  conversation_type: str,
                                  conversation_name: Optional[str] = None) -> ConversationInfo:
        """Create a conversation info object

        Args:
            conversation_id: Conversation ID
            conversation_type: Conversation type
            conversation_name: Conversation name

        Returns:
            Conversation info object
        """
        return ConversationInfo(
            conversation_id=conversation_id,
            conversation_type=conversation_type,
            conversation_name=conversation_name,
            just_started=True
        )

    async def _get_user_info(self,
                             event: Dict[str, Any],
                             conversation_info: ConversationInfo) -> UserInfo:
        """Get the user info for a given event and conversation info

        Args:
            event: Event object
            conversation_info: Conversation info object

        Returns:
            User info object
        """
        return await UserBuilder.add_user_info_to_conversation(
            self.config, event.get("message", None), conversation_info
        )

    async def _process_event(self,
                             event: Dict[str, Any],
                             conversation_info: ConversationInfo,
                             delta: ConversationDelta) -> None:
        """Process an event based on event type

        Args:
            event: Event object that should contain the following keys:
                - event_type: Type of event
                - message: Zulip message object
                - attachments: Optional attachment information
            conversation_info: Conversation info object
            delta: Delta object to update
        """
        event_type = event.get("event_type", None)
        message = event.get("message", None)

        if event_type == ZulipEventType.UPDATE_MESSAGE:
            thread_changed, thread_info = await self.thread_handler.update_thread_info(message, conversation_info)
            cached_msg = await self._update_message(message, conversation_info, thread_changed, thread_info)
            attachments = await self._update_attachment(conversation_info, event.get("attachments", []))
            cached_msg.attachments = {attachment["attachment_id"] for attachment in attachments}

            await self._update_delta_list(
                conversation_id=conversation_info.conversation_id,
                delta=delta,
                list_to_update="updated_messages",
                cached_msg=cached_msg,
                attachments=attachments
            )
            return

        if event_type == ZulipEventType.REACTION:
            await self._update_reaction(message, conversation_info, delta)

    async def _create_message(self,
                              message: Any,
                              conversation_info: ConversationInfo,
                              user_info: UserInfo,
                              thread_info: ThreadInfo) -> CachedMessage:
        """Create a new message in the cache

        Args:
            message: Zulip message object
            conversation_info: Conversation info object
            user_info: User info object
            thread_info: Thread info object

        Returns:
            Cached message object
        """
        cached_msg = await super()._create_message(
            message, conversation_info, user_info, thread_info
        )
        conversation_info.messages.add(cached_msg.message_id)

        return cached_msg

    async def _update_message(self,
                              message: Dict[str, Any],
                              conversation_info: ConversationInfo,
                              threading_changed: bool,
                              thread_info: Optional[ThreadInfo]) -> CachedMessage:
        """Update a message in the cache

        Args:
            message: Zulip message object
            conversation_info: Conversation info object
            threading_changed: Whether threading has changed
            thread_info: Thread info object

        Returns:
            Cached message object
        """
        cached_msg = await self.message_cache.get_message_by_id(
            conversation_id=conversation_info.conversation_id,
            message_id=str(message["message_id"]) if message.get("message_id", None) else None
        )

        if cached_msg:
            cached_msg.timestamp = message.get("edit_timestamp", int(datetime.now().timestamp() * 1e3))
            cached_msg.text = message.get("content", "")

            if threading_changed:
                if not thread_info:
                    self.thread_handler.remove_thread_info(conversation_info, cached_msg)
                cached_msg.reply_to_message_id = thread_info.thread_id if thread_info else None
                cached_msg.thread_id = thread_info.thread_id if thread_info else None

        return cached_msg

    async def _update_reaction(self,
                               message: Dict[str, Any],
                               conversation_info: ConversationInfo,
                               delta: ConversationDelta) -> None:
        """Update a reaction in the cache

        Args:
            message: Zulip message object
            conversation_info: Conversation info object
            delta: Delta object to update
        """
        cached_msg = await self.message_cache.get_message_by_id(
            conversation_id=conversation_info.conversation_id,
            message_id=str(message["message_id"]) if message.get("message_id", None) else None
        )

        if cached_msg:
            delta.message_id = cached_msg.message_id
            delta = ReactionHandler.update_message_reactions(message, cached_msg, delta)

    async def _get_deleted_message_ids(self, event: Dict[str, Any]) -> List[str]:
        """Get the deleted message IDs from an event

        Args:
            event: Event object

        Returns:
            List of deleted message IDs
        """
        if "deleted_ids" in event:
            return [str(id) for id in event["deleted_ids"]]
        return [str(event.get("message_id", ""))]

    async def _get_conversation_info_to_delete_from(self,
                                                    event: Any,
                                                    deleted_ids: List[str] = []) -> Optional[ConversationInfo]:
        """Get the conversation info to delete from

        Args:
            event: Event object
            deleted_ids: List of deleted message IDs (unused for Zulip)

        Returns:
            Conversation info object or None if conversation not found
        """
        return self.get_conversation(
            str(event.get("conversation_id", "")) or
            await self._get_conversation_id_from_update(event)
        )

    async def _get_conversation_to_migrate_from(self, event: Any) -> Optional[ConversationInfo]:
        """Get the old conversation from an event

        Args:
            event: Event object

        Returns:
            Conversation info object or None if conversation not found
        """
        return self.get_conversation(f"{event.get('stream_id', '')}/{event.get('orig_subject', '')}")

    async def _get_conversation_to_migrate_to(self, event: Any) -> Optional[ConversationInfo]:
        """Get the new conversation from an event

        Args:
            event: Event object

        Returns:
            Conversation info object or None if conversation not found
        """
        return await self._get_or_create_conversation_info(event)

    def _get_messages_to_migrate(self,
                                 event: Any,
                                 old_conversation: Optional[ConversationInfo] = None) -> List[str]:
        """Get the messages to migrate from an old conversation to a new conversation

        Args:
            event: Event object
            old_conversation_id: ID of the old conversation (unused for Zulip)

        Returns:
            List of message IDs
        """
        return [str(id) for id in event.get("message_ids", [])]

    def _perform_migration_related_updates(self,
                                           old_conversation_id: str,
                                           new_conversation_id: str,
                                           message_id: str) -> None:
        """Perform migration related updates

        Args:
            old_conversation_id: ID of the old conversation
            new_conversation_id: ID of the new conversation
            message_id: Message ID
        """
        self.conversations[new_conversation_id].messages.add(str(message_id))
        self.conversations[old_conversation_id].messages.discard(str(message_id))
