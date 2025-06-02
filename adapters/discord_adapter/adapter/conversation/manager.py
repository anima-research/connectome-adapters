import asyncio
import discord
import re

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from adapters.discord_adapter.adapter.conversation.data_classes import ConversationInfo
from adapters.discord_adapter.adapter.conversation.message_builder import MessageBuilder
from adapters.discord_adapter.adapter.conversation.reaction_handler import ReactionHandler
from adapters.discord_adapter.adapter.conversation.thread_handler import ThreadHandler
from adapters.discord_adapter.adapter.conversation.user_builder import UserBuilder

from core.conversation.base_data_classes import ConversationDelta, ThreadInfo, UserInfo
from core.conversation.base_manager import BaseManager
from core.cache.message_cache import CachedMessage
from core.utils.config import Config

class DiscordEventType(str, Enum):
    """Types of events that can be processed"""
    NEW_MESSAGE = "new_message"
    EDITED_MESSAGE = "edited_message"
    DELETED_MESSAGE = "deleted_message"
    ADDED_REACTION = "added_reaction"
    REMOVED_REACTION = "removed_reaction"

class Manager(BaseManager):
    """Tracks and manages information about Discord conversations"""

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
        """Get the conversation ID from a Discord message

        Args:
            message: Discord message object

        Returns:
            Conversation ID as string, or None if not found
        """
        if not message or not message.channel:
            return None

        if isinstance(message.channel, discord.DMChannel):
            return str(message.channel.id)

        channel_id = message.channel.id

        if not message.guild or not message.guild.id:
            return str(channel_id)

        return f"{message.guild.id}/{channel_id}"

    async def _get_conversation_id_from_update(self, message: Any) -> Optional[str]:
        """Get the conversation ID from a Discord updated message

        Args:
            message: Discord updated message object

        Returns:
            Conversation ID as string, or None if not found
        """
        channel_id = message.channel_id
        guild_id = message.guild_id

        return f"{guild_id}/{channel_id}" if guild_id else f"{channel_id}"

    async def _get_conversation_type(self, message: Any) -> str:
        """Get the conversation type from a Discord message

        Args:
            message: Discord message object

        Returns:
            Conversation type as string: 'dm', 'channel', or 'thread'
        """
        if isinstance(message.channel, discord.DMChannel):
            return "dm"
        if isinstance(message.channel, discord.Thread):
            return "thread"
        return "channel"

    async def _get_conversation_name(self, message: Any) -> Optional[str]:
        """Get the conversation name from a Discord message

        Args:
            message: Discord message object

        Returns:
            Conversation name as string, or None if not found
        """
        if isinstance(message.channel, discord.DMChannel):
            return None
        return message.channel.name

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
            self.config, event["message"], conversation_info
        )

    async def _process_event(self,
                             event: Dict[str, Any],
                             conversation_info: ConversationInfo,
                             delta: ConversationDelta) -> None:
        """Process an event based on event type

        Args:
            event: Event object that should contain the following keys:
                - event_type: Type of event
                - message: Discord message object
                - attachments: Optional attachment information
            conversation_info: Conversation info object
            delta: Delta object to update
        """
        event_type = event.get("event_type", None)

        if event_type == DiscordEventType.EDITED_MESSAGE:
            data = getattr(event["message"], "data", None)
            cached_msg = await self.message_cache.get_message_by_id(
                conversation_id=conversation_info.conversation_id,
                message_id=str(getattr(event["message"], "message_id", ""))
            )

            await self._update_pin_status(conversation_info, cached_msg, data, delta)
            await self._update_message(cached_msg, data, delta)
            return

        if event_type in [DiscordEventType.ADDED_REACTION, DiscordEventType.REMOVED_REACTION]:
            await self._update_reaction(event, conversation_info, delta)

    async def _create_message(self,
                              message: Any,
                              conversation_info: ConversationInfo,
                              user_info: UserInfo,
                              thread_info: ThreadInfo) -> CachedMessage:
        """Create a new message in the cache

        Args:
            message: Discord message object
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
            data: Discord message data
            delta: ConversationDelta object
        """
        if not cached_msg or not data or cached_msg.text == data.get("content", ""):
            return

        try:
            edited_timestamp = datetime.strptime(
                data.get("edited_timestamp", ""),
                "%Y-%m-%dT%H:%M:%S.%f%z"
            )
        except ValueError:
            edited_timestamp = datetime.now()

        cached_msg.timestamp = int(edited_timestamp.timestamp() * 1e3)
        cached_msg.text = data.get("content", "")
        await self._update_delta_list(
            conversation_id=cached_msg.conversation_id,
            delta=delta,
            list_to_update="updated_messages",
            cached_msg=cached_msg,
            attachments=[],
            mentions=self._get_bot_mentions(cached_msg)
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
            data: Discord message data
            delta: ConversationDelta object
        """
        if not cached_msg or not data or cached_msg.is_pinned == data.get("pinned"):
            return None

        cached_msg.is_pinned = data.get("pinned")

        if cached_msg.is_pinned:
            conversation_info.pinned_messages.add(cached_msg.message_id)
            delta.pinned_message_ids.append(cached_msg.message_id)
        else:
            conversation_info.pinned_messages.discard(cached_msg.message_id)
            delta.unpinned_message_ids.append(cached_msg.message_id)

    async def _update_reaction(self,
                               event: Any,
                               conversation_info: ConversationInfo,
                               delta: ConversationDelta) -> None:
        """Update a reaction in the cache

        Args:
            event: Event object
            conversation_info: Conversation info object
            delta: Delta object to update
        """
        message_id = str(getattr(event["message"], "message_id", ""))
        reaction = getattr(event["message"], "emoji", None)

        if not message_id or not reaction:
            return

        reaction = str(getattr(reaction, "name", ""))
        cached_msg = await self.message_cache.get_message_by_id(
            conversation_id=conversation_info.conversation_id,
            message_id=message_id
        )

        if cached_msg and reaction:
            delta.message_id = cached_msg.message_id
            ReactionHandler.update_message_reactions(
                op=event.get("event_type", ""),
                cached_msg=cached_msg,
                reaction=reaction,
                delta=delta
            )

    def _get_bot_mentions(self, cached_msg: CachedMessage) -> List[str]:
        """Get bot mentions from a cached message.
        Extracts mentions of the bot or @all from the message text.

        Args:
            cached_msg: The cached message to extract mentions from

        Returns:
            List of mentions (bot name or "all")
        """
        if not cached_msg or not cached_msg.text:
            return []

        mentions = set()
        adapter_id = self.config.get_setting("adapter", "adapter_id")

        user_mention_pattern = r"<@(\d+)>"
        found_user_mentions = re.findall(user_mention_pattern, cached_msg.text)

        # Pattern for Discord user mentions: <@USER_ID>
        for mention in found_user_mentions:
            if adapter_id and mention == adapter_id:
                mentions.add(adapter_id)

        # Check for special mentions (@everyone and @here)
        if "@everyone" in cached_msg.text or "@here" in cached_msg.text:
            mentions.add("all")

        return list(mentions)

    async def _get_deleted_message_ids(self, event: Dict[str, Any]) -> List[str]:
        """Get the deleted message IDs from an event

        Args:
            event: Event object

        Returns:
            List of deleted message IDs
        """
        return [str(getattr(event, "message_id", ""))]

    async def _get_conversation_info_to_delete_from(self,
                                                    event: Any,
                                                    deleted_ids: List[str] = []) -> Optional[ConversationInfo]:
        """Get the conversation info to delete from

        Args:
            event: Event object
            deleted_ids: List of deleted message IDs (unused for Discord)

        Returns:
            Conversation info object or None if conversation not found
        """
        return self.get_conversation(
            await self._get_conversation_id_from_update(event)
        )
