import asyncio
import re

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from src.adapters.slack_adapter.conversation.data_classes import ConversationInfo
from src.adapters.slack_adapter.conversation.message_builder import MessageBuilder
from src.adapters.slack_adapter.conversation.reaction_handler import ReactionHandler
from src.adapters.slack_adapter.conversation.thread_handler import ThreadHandler

from src.core.conversation.base_data_classes import ConversationDelta, ThreadInfo, UserInfo
from src.core.conversation.base_manager import BaseManager
from src.core.cache.message_cache import CachedMessage
from src.core.utils.config import Config

class SlackEventType(str, Enum):
    """Types of events that can be processed"""
    NEW_MESSAGE = "message"
    EDITED_MESSAGE = "edited_message"
    REACTION = "reaction"
    PIN = "pin"

class Manager(BaseManager):
    """Tracks and manages information about Slack conversations"""

    async def update_metadata(self, event: Any) -> List[Dict[str, Any]]:
        """Update the conversation metadata

        Args:
            event: Event object

        Returns:
            Dictionary with delta information
        """
        deltas = []
        update_type = event.get("type", "")
        team_id = event.get("team", "")
        channel = event.get("channel", {})
        platform_conversation_id = f"{event.get('team', '')}/{channel.get('id', '')}"

        if update_type == "team_rename":
            new_name = event.get("name", "")
        else:
            new_name = channel.get("name", "")

        for conversation in self.conversations.values():
            if update_type == "team_rename":
                updated = self._update_server_metadata(conversation, team_id, new_name)
            else:
                updated = self._update_conversation_metadata(conversation, platform_conversation_id, new_name)

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

    async def _get_platform_conversation_id(self, message: Any) -> Optional[str]:
        """Get the conversation ID from a Slack message

        Args:
            message: Slack message object

        Returns:
            Conversation ID as string, or None if not found
        """
        if not message:
            return None

        if "conversation_id" in message:
            return message.get("conversation_id", None)

        team_id = message.get("team", "")
        channel_id = (
            message.get("channel", "") or
            message.get("item", {}).get("channel", "")
        )

        if not team_id or not channel_id:
            return None

        return f"{team_id}/{channel_id}"

    async def _get_conversation_id_from_update(self, message: Any) -> Optional[str]:
        """Get the conversation ID from a Slack updated message

        Args:
            message: Slack updated message object

        Returns:
            Conversation ID as string, or None if not found
        """
        platform_conversation_id = await self._get_platform_conversation_id(message)
        if not platform_conversation_id:
            return None

        return self._generate_deterministic_conversation_id(platform_conversation_id)

    async def _get_conversation_type(self, message: Any) -> str:
        """Get the conversation type from a Slack message

        Args:
            message: Slack message object

        Returns:
            Conversation type as string: 'im', 'mpim', 'channel', or 'group'
        """
        if not message:
            return None

        return message.get("channel_type", "")

    async def _update_conversation_name(self, event: Any, conversation_info: Any) -> None:
        """Update the conversation name

        Args:
            event: Event object
            conversation_info: Conversation info object

        Returns:
            Conversation name as string, or None if not found
        """
        if event.get("platform_conversation", None) and conversation_info.conversation_type in ["channel", "group"]:
            conversation_info.conversation_name = event["platform_conversation"].get("name", None)
            return

        conversation_info.conversation_name = self._get_custom_conversation_name(conversation_info)

    def _create_conversation_info(self,
                                  platform_conversation_id: str,
                                  conversation_id: str,
                                  conversation_type: str,
                                  server: Optional[Any] = None) -> ConversationInfo:
        """Create a conversation info object

        Args:
            platform_conversation_id: Platform conversation ID
            conversation_id: Conversation ID
            conversation_type: Conversation type
            server: Server object

        Returns:
            Conversation info object
        """
        server_id = server.get("id", None) if server else None
        server_name = server.get("name", None) if server else None

        return ConversationInfo(
            platform_conversation_id=platform_conversation_id,
            conversation_id=conversation_id,
            conversation_type=conversation_type,
            server_id=server_id,
            server_name=server_name,
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
                - message: Slack message object
                - attachments: Optional attachment information
            conversation_info: Conversation info object
            delta: Delta object to update
        """
        event_type = event.get("event_type", None)
        message_id = (
            event["message"].get("previous_message", {}) or
            event["message"].get("item", {}).get("message", {}) or
            event["message"].get("item", {})
        ).get("ts", "")
        cached_msg = await self.cache.message_cache.get_message_by_id(
            conversation_id=conversation_info.conversation_id,
            message_id=message_id
        )

        if not cached_msg:
            return

        if event_type == SlackEventType.EDITED_MESSAGE:
            await self._update_message(event, cached_msg, delta)
        elif event_type == SlackEventType.REACTION:
            await self._update_reaction(event["message"], cached_msg, delta)
        elif event_type == SlackEventType.PIN:
            await self._update_pin_status(
                conversation_info, cached_msg, event["message"], delta
            )

    async def _create_message(self,
                              event: Any,
                              conversation_info: ConversationInfo,
                              thread_info: ThreadInfo) -> CachedMessage:
        """Create a new message in the cache

        Args:
            event: Slack event object
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
                              cached_msg: CachedMessage,
                              delta: ConversationDelta) -> None:
        """Update a message in the cache

        Args:
            event: Slack event object
            cached_msg: CachedMessage object
            delta: ConversationDelta object
        """
        message = event.get("message", None)
        updated_content = event.get("updated_content", None)

        if not cached_msg or not message:
            return

        cached_msg.text = updated_content if updated_content else message.get("message", {}).get("text", "")
        cached_msg.edit_timestamp = int(datetime.now().timestamp())
        cached_msg.edited = True
        await self._update_delta_list(
            conversation_id=cached_msg.conversation_id,
            delta=delta,
            list_to_update="updated_messages",
            cached_msg=cached_msg,
            attachments=[],
            mentions=event.get("mentions", [])
        )

    async def _update_pin_status(self,
                                 conversation_info: ConversationInfo,
                                 cached_msg: CachedMessage,
                                 data: Any,
                                 delta: ConversationDelta) -> None:
        """Update the pin status of a message

        Args:
            conversation_info: Conversation info object
            cached_msg: CachedMessage object
            data: Slack message data
            delta: ConversationDelta object
        """
        if not cached_msg or not data or not data.get("type", ""):
            return None

        if data["type"] == "pin_added":
            cached_msg.is_pinned = True
            conversation_info.pinned_messages.add(cached_msg.message_id)
            delta.pinned_message_ids.append(cached_msg.message_id)
        elif data["type"] == "pin_removed":
            cached_msg.is_pinned = False
            conversation_info.pinned_messages.discard(cached_msg.message_id)
            delta.unpinned_message_ids.append(cached_msg.message_id)

    async def _update_reaction(self,
                               event: Any,
                               cached_msg: CachedMessage,
                               delta: ConversationDelta) -> None:
        """Update a reaction in the cache

        Args:
            event: Event object
            cached_msg: CachedMessage object
            delta: Delta object to update
        """
        reaction = event.get("reaction", "")

        if reaction:
            delta.message_id = cached_msg.message_id
            ReactionHandler.update_message_reactions(
                op=event.get("type", ""),
                cached_msg=cached_msg,
                reaction=reaction,
                delta=delta
            )

    async def _get_deleted_message_ids(self, event: Dict[str, Any]) -> List[str]:
        """Get the deleted message IDs from an event

        Args:
            event: Event object

        Returns:
            List of deleted message IDs
        """
        message_id = str(event.get("previous_message", {}).get("ts", ""))

        if not message_id:
            return []

        return [message_id]

    async def _get_conversation_info_to_delete_from(self,
                                                    event: Any,
                                                    deleted_ids: List[str] = []) -> Optional[ConversationInfo]:
        """Get the conversation info to delete from

        Args:
            event: Slack event object
            deleted_ids: List of deleted message IDs (unused for Slack)

        Returns:
            Conversation info object or None if conversation not found
        """
        platform_conversation_id = await self._get_platform_conversation_id(event)
        if not platform_conversation_id:
            return None

        return self.get_conversation(
            self._generate_deterministic_conversation_id(platform_conversation_id)
        )
