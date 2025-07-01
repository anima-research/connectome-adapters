import asyncio
import discord
import re

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from src.adapters.discord_adapter.conversation.data_classes import ConversationInfo
from src.adapters.discord_adapter.conversation.message_builder import MessageBuilder
from src.adapters.discord_adapter.conversation.reaction_handler import ReactionHandler
from src.adapters.discord_adapter.conversation.thread_handler import ThreadHandler
from src.adapters.discord_adapter.conversation.user_builder import UserBuilder

from src.core.conversation.base_data_classes import ConversationDelta, ThreadInfo, UserInfo
from src.core.conversation.base_manager import BaseManager
from src.core.cache.message_cache import CachedMessage
from src.core.utils.config import Config

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

    async def update_metadata(self, event: Any) -> List[Dict[str, Any]]:
        """Update the conversation metadata

        Args:
            event: Event object

        Returns:
            Dictionary with delta information
        """
        deltas = []
        server_id = None
        platform_conversation_id = None
        new_name = event.name

        if hasattr(event, "guild"):
            platform_conversation_id = f"{event.guild.id}/{event.id}"
        else:
            server_id = str(event.id)

        for conversation in self.conversations.values():
            if server_id:
                updated = self._update_server_metadata(conversation, server_id, new_name)
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

    async def _get_platform_conversation_id(self, message: Any) -> Optional[str]:
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
        return self._generate_deterministic_conversation_id(
            f"{guild_id}/{channel_id}" if guild_id else f"{channel_id}"
        )

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

    async def _update_conversation_name(self, event: Any, conversation_info: Any) -> None:
        """Update the conversation name

        Args:
            event: Event object
            conversation_info: Conversation info object

        Returns:
            Conversation name as string, or None if not found
        """
        if isinstance(event["message"].channel, discord.DMChannel):
            conversation_info.conversation_name = self._get_custom_conversation_name(conversation_info)
            return

        conversation_info.conversation_name = event["message"].channel.name

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
        server_id = str(server.id) if server else None
        server_name = server.name if server else None

        return ConversationInfo(
            platform_conversation_id=platform_conversation_id,
            conversation_id=conversation_id,
            conversation_type=conversation_type,
            server_id=server_id,
            server_name=server_name,
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
            cached_msg = await self.message_cache.get_message_by_id(
                conversation_id=conversation_info.conversation_id,
                message_id=str(getattr(event["message"], "message_id", ""))
            )

            await self._update_pin_status(conversation_info, cached_msg, event["message"], delta)
            await self._update_message(cached_msg, event["message"], delta)
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
                              message: Any,
                              delta: ConversationDelta) -> None:
        """Update a message in the cache

        Args:
            cached_msg: CachedMessage object
            message: Discord message object
            delta: ConversationDelta object
        """
        data = getattr(message, "data", None)
        platform_cached_msg = getattr(message, "cached_message", None)

        if not cached_msg or not data or cached_msg.text == data.get("content", ""):
            return

        try:
            edit_timestamp = datetime.strptime(
                data.get("edit_timestamp", ""),
                "%Y-%m-%dT%H:%M:%S.%f%z"
            )
        except ValueError:
            edit_timestamp = datetime.now()

        cached_msg.edit_timestamp = int(edit_timestamp.timestamp())
        cached_msg.edited = True
        cached_msg.text = data.get("content", "")
        await self._update_delta_list(
            conversation_id=cached_msg.conversation_id,
            delta=delta,
            list_to_update="updated_messages",
            cached_msg=cached_msg,
            attachments=[],
            mentions=self._get_bot_mentions(
                cached_msg,
                message if not platform_cached_msg else platform_cached_msg
            )
        )

    async def _update_pin_status(self,
                                 conversation_info: ConversationInfo,
                                 cached_msg: CachedMessage,
                                 message: Any,
                                 delta: ConversationDelta) -> None:
        """Update the pin status of a message

        Args:
            conversation_info: Conversation info object
            cached_msg: CachedMessage object
            message: Discord message object
            delta: ConversationDelta object
        """
        data = getattr(message, "data", None)

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

    def _get_bot_mentions(self, cached_msg: CachedMessage, message: Any) -> List[str]:
        """Get bot mentions from a cached message.
        Extracts mentions of the bot or @all from the message text.
        Also checks if the message is a reply to the bot.

        Args:
            cached_msg: The cached message to extract mentions from
            message: Raw message object from the adapter

        Returns:
            List of mentions (bot name or "all")
        """
        if not cached_msg or not cached_msg.text:
            return []

        mentions = set()
        adapter_id = self.config.get_setting("adapter", "adapter_id")

        # Check if the message is a reply to the bot
        if message.reference and message.reference.resolved:
            if isinstance(message.reference.resolved, discord.Message):
                if message.reference.resolved.author.id == int(adapter_id):
                    mentions.add(adapter_id)

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
        return self.get_conversation(await self._get_conversation_id_from_update(event))
