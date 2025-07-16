import asyncio
import discord
import logging
import os
import re

from typing import Any, Dict, List, Optional

from src.core.cache.cache import Cache
from src.core.cache.user_cache import UserInfo
from src.core.utils.config import Config

class UserInfoPreprocessor:
    """Processes information about users in Discord events"""

    def __init__(self, config: Config, client: Any):
        """Initialize the processor

        Args:
            config: The configuration
            client: The client
        """
        self.config = config
        self.client = client
        self.cache = Cache.get_instance()
        self.adapter_id = self.config.get_setting("adapter", "adapter_id")
        self.author_id = None
        self.updated_content = ""
        self.mentions = set()

    async def process_incoming_event(self, message: Any) -> Dict[str, Any]:
        """Collect users' details for a Discord event

        Args:
            message: Discord message

        Returns:
            Dict of details
        """
        if message and hasattr(message, "author") and message.author:
            user = message.author
            self.author_id = str(user.id)
            self._get_or_create_user(self.author_id, user)

        await self._add_mentioned_users_to_cache_and_update_content(message)

        return {
            "user_id": self.author_id,
            "updated_content": self.updated_content,
            "mentions": list(self.mentions)
        }

    async def _add_mentioned_users_to_cache_and_update_content(self, message: Any) -> None:
        """Get mentions from a Discord message.
        Extracts mentions of the bot or @all from the message text.
        Also checks if the message is a reply to the bot.
        Adds the users to the cache and updates the message content.

        Args:
            message: a Discord message object
        """
        if not message:
            return

        # Check if the message is a reply to the bot
        if hasattr(message, "reference") and message.reference and message.reference.resolved:
            if isinstance(message.reference.resolved, discord.Message):
                if message.reference.resolved.author.id == int(self.adapter_id):
                    self.mentions.add(self.adapter_id)

        content = ""
        if hasattr(message, "content") and message.content:
            content = message.content
        elif hasattr(message, "data") and message.data:
            content = message.data.get("content", "")
        self.updated_content = content

        user_mention_pattern = r"<@(\d+)>"
        found_user_mentions = re.findall(user_mention_pattern, content)

        # Pattern for Discord user mentions: <@USER_ID>
        for mention in found_user_mentions:
            user = self._get_or_create_user(mention, await self.client.fetch_user(mention))

            if self.adapter_id and mention == self.adapter_id:
                self.mentions.add(self.adapter_id)

            # Replace the mention with the user's display name
            mention_regex = f"<@{mention}>"
            self.updated_content = re.sub(mention_regex, f"<@{user.display_name}>", self.updated_content)

        # Check for special mentions (@everyone and @here)
        if "@everyone" in content or "@here" in content:
            self.mentions.add("all")

    def _get_or_create_user(self, user_id: str, user: Optional[Any] = None) -> Optional[UserInfo]:
        """Get a user from the cache or create a new one if it doesn't exist.

        Args:
            user_id: The ID of the user
            user: The user object
        """
        if not user_id:
            return None

        if user_id not in self.cache.user_cache.users:
            self.cache.user_cache.add_user({
                "user_id": user_id,
                "username": user.name,
                "is_bot": self.adapter_id == user_id
            })

        return self.cache.user_cache.users[user_id]

    async def process_outgoing_event(self,
                                     mentions: List[str],
                                     text: str) -> str:
        """Process an outgoing event. Mention users in a message

        Args:
            mentions: List of user ids to mention
            text: Message text

        Returns:
            str: Message text with users mentioned
        """
        if not mentions:
            return text

        users = ""

        for mention in mentions:
            if mention == "all":
                users += self._adapter_specific_mention_all()
                continue

            user_info = Cache.get_instance().user_cache.get_user_by_id(mention)
            if user_info:
                users += self._adapter_specific_mention_user(user_info)

        return users + text

    def _adapter_specific_mention_all(self) -> str:
        """Mention all users in a conversation

        Returns:
            str: Mention all users in a conversation
        """
        return "@here "

    def _adapter_specific_mention_user(self, user_info: UserInfo) -> str:
        """Mention a user in a conversation

        Args:
            user_info: User info

        Returns:
            str: Mention a user in a conversation
        """
        return f"<@{user_info.user_id}> "
