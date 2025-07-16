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
        self.adapter_email = self.config.get_setting("adapter", "adapter_email")
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
            self.author_id = str(event.get("sender_id", ""))

            if event.get("type", None) == "private":
                recipients = event.get("display_recipient", [])
                if isinstance(recipients, list):
                    for recipient in recipients:
                        self._get_or_create_user(
                            str(recipient.get("id", "")),
                            recipient.get("full_name", None),
                            recipient.get("email", None)
                        )
            else:
                self._get_or_create_user(
                    str(event.get("sender_id", "")),
                    event.get("sender_full_name", None),
                    event.get("sender_email", None)
                )

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

        content = event.get("content", "")
        self.updated_content = content

        # Simple pattern for bot and all mentions: @**Name**
        simple_mention_pattern = r"@\*\*(.*?)\*\*"
        simple_mentions = re.findall(simple_mention_pattern, content)
        for mention in simple_mentions:
            if mention.lower() == "all":
                self.mentions.add("all")
            elif self.adapter_name and mention == self.adapter_name:
                self.mentions.add(self.adapter_id)

            mention_regex = f"@\*\*{mention}\*\*"
            self.updated_content = re.sub(mention_regex, f"<@{mention}>", self.updated_content)

        # User ID pattern for mentions: @_**Name|ID**
        user_id_mention_pattern = r"@_\*\*(.*?)\|(.*?)\*\*"
        user_id_mentions = re.findall(user_id_mention_pattern, content)
        for username, user_id in user_id_mentions:
            if self.adapter_id and user_id == self.adapter_id:
                self.mentions.add(self.adapter_id)

            mention_regex = f"@_\*\*{username}\|(.*?)\*\*"
            self.updated_content = re.sub(mention_regex, f"<@{username}>", self.updated_content)

    def _get_or_create_user(self,
                            user_id: str,
                            username: Optional[str] = None,
                            email: Optional[str] = None) -> Optional[UserInfo]:
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
                "username": username,
                "email": email,
                "is_bot": self._received_from_adapter(user_id, email)
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
        return "@**all** "

    def _adapter_specific_mention_user(self, user_info: UserInfo) -> str:
        """Mention a user in a conversation

        Args:
            user_info: User info

        Returns:
            str: Mention a user in a conversation
        """
        return f"@**{user_info.display_name}** "

    def _received_from_adapter(self, id: str, email: str) -> bool:
        """Check if the message is from the adapter

        Args:
            config: Config object
            id: User ID
            email: User email

        Returns:
            True if the message is from the adapter, False otherwise
        """
        return self.adapter_id == id and self.adapter_email == email
