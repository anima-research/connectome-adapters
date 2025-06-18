import asyncio
import re

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from src.adapters.slack_adapter.conversation.data_classes import ConversationInfo
from src.adapters.slack_adapter.conversation.message_builder import MessageBuilder
from src.adapters.slack_adapter.conversation.reaction_handler import ReactionHandler
from src.adapters.slack_adapter.conversation.thread_handler import ThreadHandler
from src.adapters.slack_adapter.conversation.user_builder import UserBuilder

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

    def __init__(self, config: Config, start_maintenance=False):
        """Initialize the conversation manager

        Args:
            config: Config instance
            start_maintenance: Whether to start the maintenance loop
        """
        super().__init__(config, start_maintenance)
        self.message_builder = MessageBuilder()
        self.thread_handler = ThreadHandler(self.message_cache)

    async def _get_conversation_id(self, message: Any) -> Optional[str]:
        """Get the conversation ID from a Slack message

        Args:
            message: Slack message object

        Returns:
            Conversation ID as string, or None if not found
        """
        if not message:
            return None

        conversation_id = message.get("conversation_id", "")
        if conversation_id:
            return conversation_id

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
        return await self._get_conversation_id(message)

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

    async def _get_conversation_name(self, message: Any) -> Optional[str]:
        """Get the conversation name from a Slack message

        Args:
            message: Slack message object

        Returns:
            None because Slack doesn't have conversation names
        """
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
            event: Dictionary containing the event data
            conversation_info: Conversation info object

        Returns:
            User info object
        """
        return await UserBuilder.add_user_info_to_conversation(
            self.config, event["user"], conversation_info
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
        cached_msg = await self.message_cache.get_message_by_id(
            conversation_id=conversation_info.conversation_id,
            message_id=message_id
        )

        if not cached_msg:
            return

        if event_type == SlackEventType.EDITED_MESSAGE:
            await self._update_message(cached_msg, event["message"], delta)
        elif event_type == SlackEventType.REACTION:
            await self._update_reaction(event["message"], cached_msg, delta)
        elif event_type == SlackEventType.PIN:
            await self._update_pin_status(
                conversation_info, cached_msg, event["message"], delta
            )

    async def _create_message(self,
                              message: Any,
                              conversation_info: ConversationInfo,
                              user_info: UserInfo,
                              thread_info: ThreadInfo) -> CachedMessage:
        """Create a new message in the cache

        Args:
            message: Slack message object
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
                              cached_msg: CachedMessage,
                              data: Any,
                              delta: ConversationDelta) -> None:
        """Update a message in the cache

        Args:
            cached_msg: CachedMessage object
            data: Slack message data
            delta: ConversationDelta object
        """
        if not cached_msg or not data:
            return

        cached_msg.text = data.get("message", {}).get("text", "")
        cached_msg.edit_timestamp = int(datetime.now().timestamp())
        cached_msg.edited = True
        await self._update_delta_list(
            conversation_id=cached_msg.conversation_id,
            delta=delta,
            list_to_update="updated_messages",
            cached_msg=cached_msg,
            attachments=[],
            mentions=self._get_bot_mentions(cached_msg, data.get("message", {}))
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

    def _get_bot_mentions(self, cached_msg: CachedMessage, message: Any) -> List[str]:
        """Get bot mentions from a cached message.
        Extracts mentions of the bot or @all from the message text.

        Args:
            cached_msg: The cached message to extract mentions from
            message: The Slack message object

        Returns:
            List of mentions (bot name or "all")
        """
        if not cached_msg or not cached_msg.text:
            return []

        mentions = set()
        adapter_id = self.config.get_setting("adapter", "adapter_id")

        mention_pattern = r"<@([\w\d]+)>"
        found_mentions = re.findall(mention_pattern, cached_msg.text)

        # Pattern for Slack user mentions: <@USER_ID>
        for mention in found_mentions:
            if adapter_id and mention == adapter_id:
                mentions.add(adapter_id)

        # Check for special mentions (<!here> and <!channel>)
        if "<!here>" in cached_msg.text or "<!channel>" in cached_msg.text:
            mentions.add("all")

        return list(mentions)

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
        return self.get_conversation(await self._get_conversation_id(event))
