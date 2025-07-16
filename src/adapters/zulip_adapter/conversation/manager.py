import asyncio
import re

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from src.adapters.zulip_adapter.conversation.data_classes import ConversationInfo
from src.adapters.zulip_adapter.conversation.message_builder import MessageBuilder
from src.adapters.zulip_adapter.conversation.reaction_handler import ReactionHandler
from src.adapters.zulip_adapter.conversation.thread_handler import ThreadHandler

from src.core.conversation.base_data_classes import BaseConversationInfo, ConversationDelta, ThreadInfo
from src.core.conversation.base_manager import BaseManager
from src.core.cache.message_cache import CachedMessage
from src.core.utils.config import Config

class ZulipEventType(str, Enum):
    """Types of events that can be processed"""
    MESSAGE = "message"
    UPDATE_MESSAGE = "update_message"
    REACTION = "reaction"

class Manager(BaseManager):
    """Tracks and manages information about Zulip conversations"""

    def get_conversation(self, conversation_id: str) -> Optional[BaseConversationInfo]:
        """Get the conversation info for a given conversation ID

        Args:
            conversation_id: The ID of the conversation to get info for

        Returns:
            The conversation info for the given conversation ID, or None if it doesn't exist
        """
        adapter_type = self.config.get_setting("adapter", "adapter_type")

        if conversation_id and not conversation_id.startswith(f"{adapter_type}_"):
            conversation_id = self._generate_deterministic_conversation_id(conversation_id)

        return self.conversations.get(conversation_id, None)

    async def migrate_between_conversations(self, event: Any) -> Dict[str, Any]:
        """Handle a supergroup that was migrated from a regular group

        Args:
            event: Zulip event object

        Returns:
            Dictionary with delta information
        """
        message = event["message"]
        message.update({"type": "stream"})
        server = event["server"]

        old_platform_conversation_id = f"{message.get('stream_id', '')}/{message.get('orig_subject', '')}"
        old_conversation = self.get_conversation(
            self._generate_deterministic_conversation_id(old_platform_conversation_id)
        )
        new_conversation = await self._get_or_create_conversation_info(event)

        if not new_conversation:
            return {}

        new_conversation.server_name = server.get("realm_name", None) if server else None
        if not new_conversation.conversation_name:
            await self._update_conversation_name(event, new_conversation)

        async with self._lock:
            delta = self._create_conversation_delta(message, new_conversation)
            messages = [str(id) for id in message.get("message_ids", [])]

            if not old_conversation:
                return delta.to_dict()

            for message_id in messages:
                old_cached_msg = await self.cache.message_cache.get_message_by_id(
                    old_conversation.conversation_id,
                    message_id
                )

                if not old_cached_msg:
                    continue

                delta.deleted_message_ids.append(message_id)
                attachment_ids = old_cached_msg.attachments.copy()
                await self.cache.message_cache.migrate_message(
                    old_conversation.conversation_id,
                    new_conversation.conversation_id,
                    message_id
                )
                self.conversations[new_conversation.conversation_id].messages.add(str(message_id))
                self.conversations[old_conversation.conversation_id].messages.discard(str(message_id))

                for attachment_id in attachment_ids:
                    new_conversation.attachments.add(attachment_id)

                    attachment = self.cache.attachment_cache.get_attachment(attachment_id)
                    if attachment:
                        attachment.conversations.add(new_conversation.conversation_id)

                    still_referenced = False
                    if old_conversation.conversation_id in self.cache.message_cache.messages:
                        for other_msg_id, other_msg in self.cache.message_cache.messages[old_conversation.conversation_id].items():
                            if other_msg_id != message_id and attachment_id in other_msg.attachments:
                                still_referenced = True
                                break

                    if not still_referenced:
                        old_conversation.attachments.discard(attachment_id)
                        if attachment:
                            attachment.conversations.discard(old_conversation.conversation_id)

                if not delta.fetch_history:
                    await self._update_delta_list(
                        conversation_id=new_conversation.conversation_id,
                        delta=delta,
                        list_to_update="added_messages",
                        message_id=message_id
                    )

        return delta.to_dict()

    async def update_metadata(self, event: Any) -> List[Dict[str, Any]]:
        """Update the conversation metadata

        Args:
            event: Event object

        Returns:
            List of delta information
        """
        if event.get("op", None) != "update" or event.get("property", None) != "name":
            return []

        deltas = []
        new_name = event.get("value", None)
        stream_id = None

        if event.get("type", None) != "realm":
            stream_id = str(event.get("stream_id", ""))

        for conversation in self.conversations.values():
            updated = False

            if not stream_id:
                conversation.server_name = new_name
                updated = True
            elif conversation.stream_id == stream_id and conversation.stream_name != new_name:
                conversation.stream_name = new_name
                conversation.set_stream_conversation_name()
                updated = True

            if updated:
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

    async def _get_or_create_conversation_info(self, event: Any) -> Optional[BaseConversationInfo]:
        """Get existing conversation info or create a new one

        Args:
            event: Event object

        Returns:
           Conversation info object or None if conversation can't be determined
        """
        conversation_info = await super()._get_or_create_conversation_info(event)

        if conversation_info and conversation_info.conversation_type == "stream":
            conversation_info.stream_id = str(event["message"].get("stream_id", None))

            if "display_recipient" in event["message"]:
                conversation_info.stream_name = event["message"].get("display_recipient")
            else:
                conversation_info.stream_name = event["message"].get("stream_name", None)

            conversation_info.stream_topic = event["message"].get("subject", None)

        return conversation_info

    async def _get_platform_conversation_id(self, message: Any) -> Optional[str]:
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

    async def _update_conversation_name(self, _: Any, conversation_info: Any) -> None:
        """Update the conversation name

        Args:
            event: Event object
            conversation_info: Conversation info object

        Returns:
            Conversation name as string, or None if not found
        """
        if conversation_info.conversation_type == "stream":
            conversation_info.set_stream_conversation_name()
        else:
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
            server: Server object

        Returns:
            Conversation info object
        """
        return ConversationInfo(
            platform_conversation_id=platform_conversation_id,
            conversation_id=conversation_id,
            conversation_type=conversation_type,
            server_id=None,
            server_name=server.get("realm_name", None) if server else None,
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
                - message: Zulip message object
                - attachments: Optional attachment information
            conversation_info: Conversation info object
            delta: Delta object to update
        """
        event_type = event.get("event_type", None)
        message = event.get("message", None)

        if event_type == ZulipEventType.UPDATE_MESSAGE:
            thread_changed, thread_info = await self.thread_handler.update_thread_info(message, conversation_info)
            cached_msg = await self._update_message(event, conversation_info, thread_changed, thread_info)
            attachments = await self._update_attachment(conversation_info, event.get("attachments", []))
            cached_msg.attachments = {attachment["attachment_id"] for attachment in attachments}

            await self._update_delta_list(
                conversation_id=conversation_info.conversation_id,
                delta=delta,
                list_to_update="updated_messages",
                cached_msg=cached_msg,
                attachments=attachments,
                mentions=event.get("mentions", [])
            )
            return

        if event_type == ZulipEventType.REACTION:
            await self._update_reaction(message, conversation_info, delta)

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
        conversation_info.messages.add(cached_msg.message_id)

        return cached_msg

    async def _update_message(self,
                              event: Any,
                              conversation_info: ConversationInfo,
                              threading_changed: bool,
                              thread_info: Optional[ThreadInfo]) -> CachedMessage:
        """Update a message in the cache

        Args:
            event: Event object
            conversation_info: Conversation info object
            threading_changed: Whether threading has changed
            thread_info: Thread info object

        Returns:
            Cached message object
        """
        message = event.get("message", None)
        cached_msg = await self.cache.message_cache.get_message_by_id(
            conversation_id=conversation_info.conversation_id,
            message_id=str(message["message_id"]) if message.get("message_id", None) else None
        )

        if cached_msg:
            cached_msg.edit_timestamp = message.get("edit_timestamp", int(datetime.now().timestamp()))
            cached_msg.edited = True

            if "updated_content" in event and event["updated_content"]:
                cached_msg.text = event["updated_content"]
            else:
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
        cached_msg = await self.cache.message_cache.get_message_by_id(
            conversation_id=conversation_info.conversation_id,
            message_id=str(message["message_id"]) if message.get("message_id", None) else None
        )

        if cached_msg:
            delta.message_id = cached_msg.message_id
            ReactionHandler.update_message_reactions(message, cached_msg, delta)

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
