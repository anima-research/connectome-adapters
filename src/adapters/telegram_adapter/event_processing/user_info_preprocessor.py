import asyncio
import logging
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
        self.adapter_name = self.config.get_setting("adapter", "adapter_name")
        self.author_id = None
        self.updated_content = ""
        self.mentions = set()

    async def process_incoming_event(self, event: Any) -> Dict[str, Any]:
        """Collect users' details for a Telegram event

        Args:
            event: Telegram event

        Returns:
            Dict of details
        """
        if event:
            user = await self._get_platform_user_info(self._get_user_id_from_event(event))
            self.author_id = str(getattr(user, "id", ""))
            self._get_or_create_user(self.author_id, user)

        await self._retrieve_mentions_and_update_content(event)

        return {
            "user_id": self.author_id,
            "updated_content": self.updated_content,
            "mentions": list(self.mentions)
        }

    async def _retrieve_mentions_and_update_content(self, event: Any) -> None:
        """Get mentions from a Telegram message.

        Args:
            event: a Telegram event object
        """
        if not event:
            return

        content = getattr(event, "message", "")
        self.updated_content = content
        user_mention_pattern = r"@(\w+)"

        if content:
            for mention in re.findall(user_mention_pattern, content):
                if self.adapter_name and mention == self.adapter_name:
                    self.mentions.add(self.adapter_id)

                mention_regex = f"@{mention}"
                self.updated_content = re.sub(mention_regex, f"<@{mention}>", self.updated_content)

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
                "first_name": getattr(user, "first_name", None),
                "last_name": getattr(user, "last_name", None),
                "username": getattr(user, "username", None),
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
        return ""

    def _adapter_specific_mention_user(self, user_info: UserInfo) -> str:
        """Mention a user in a conversation

        Args:
            user_info: User info

        Returns:
            str: Mention a user in a conversation
        """
        return f"@{user_info.username} " if user_info.username else ""

    def _get_user_id_from_event(self, message: Any) -> Optional[Any]:
        """Get user ID from a Telegram event

        Args:
            message: Telethon message object

        Returns:
            Telegram user ID or None if not found
        """
        if message and hasattr(message, "from_id") and hasattr(message.from_id, "user_id"):
            return message.from_id.user_id
        if message and hasattr(message, "peer_id") and hasattr(message.peer_id, "user_id"):
            return message.peer_id.user_id
        return None

    async def _get_platform_user_info(self, user_id: str) -> Any:
        """Get user info for a given event

        Args:
            user_id: Telegram user id

        Returns:
            User info object
        """
        try:
            return await self.client.get_entity(int(user_id))
        except Exception as e:
            logging.error(f"Error fetching user info: {e}")

        return {}
