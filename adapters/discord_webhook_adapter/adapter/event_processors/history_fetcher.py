import asyncio
import discord
import logging
import os

from typing import Any, Dict, List, Optional

from adapters.discord_webhook_adapter.adapter.conversation.manager import Manager
from core.event_processors.base_history_fetcher import BaseHistoryFetcher
from core.rate_limiter.rate_limiter import RateLimiter
from core.utils.config import Config

class HistoryFetcher(BaseHistoryFetcher):
    """Fetches and formats history from Discord"""

    def __init__(self,
                 config: Config,
                 client: Any,
                 conversation_manager: Manager,
                 conversation_id: str,
                 anchor: Optional[str] = None,
                 before: Optional[int] = None,
                 after: Optional[int] = None,
                 history_limit: Optional[int] = None):
        """Initialize the Discord webhook HistoryFetcher

        Args:
            config: Config instance
            client: Discord client
            conversation_manager: ConversationManager instance
            conversation_id: Conversation ID
            anchor: Anchor message ID
            before: Before datetime
            after: After datetime
            history_limit: Limit the number of messages to fetch
        """
        super().__init__(
            config,
            client,
            conversation_manager,
            conversation_id,
            anchor,
            before,
            after,
            history_limit
        )
        self.conversation_id = conversation_id

    async def fetch(self) -> List[Dict[str, Any]]:
        """Fetch conversation history

        Returns:
            List of formatted message history
        """
        return await self._fetch_from_api()

    async def _fetch_from_api(self) -> List[Dict[str, Any]]:
        """Fetch conversation history via API

        Returns:
            List of formatted message history
        """
        if not self.client or not (self.before or self.after):
            logging.error("No bot client or no before/after to fetch history")
            return []

        try:
            channel = await self._get_channel()
            if not channel:
                logging.error("No conversation channel to fetch history")
                return []

            result = []
            if self.before:
                result = await self._fetch_history_in_batches(channel, 0)
            elif self.after:
                result = await self._fetch_history_in_batches(channel, -1)

            return self._filter_and_limit_messages(
                await self._parse_fetched_history(result)
            )
        except Exception as e:
            logging.error(f"Error fetching conversation history: {e}", exc_info=True)
            return []

    async def _get_channel(self) -> Optional[Any]:
        """Get a Discord channel object

        Returns:
            Discord channel object or None if not found
        """
        await self.rate_limiter.limit_request("fetch_channel")

        channel_id = int(self.conversation_id.split("/")[-1])
        channel = self.client.get_channel(channel_id) or await self.client.fetch_channel(channel_id)

        if not channel:
            raise Exception(f"Channel {channel_id} not found")

        return channel

    async def _fetch_history_in_batches(self, channel: Any, index: int) -> List[Any]:
        """Fetch history in batches

        Args:
            channel: Discord channel object
            index: Index of the batch

        Returns:
            List of messages
        """
        max_iterations = self.config.get_setting("adapter", "max_pagination_iterations")
        limit = self.config.get_setting("adapter", "max_history_limit")
        result = []

        for _ in range(max_iterations):
            if len(result) > self.history_limit * 2:
                timestamp_1 = int(result[0].created_at.timestamp() * 1e3)
                timestamp_2 = int(result[-1].created_at.timestamp() * 1e3)

                if self.before and timestamp_1 < self.before <= timestamp_2:
                    break
                if self.after and timestamp_1 <= self.after < timestamp_2:
                    break

            kwargs = {"limit": limit}
            if not self.anchor:
                kwargs["oldest_first"] = True
            elif index >= 0:
                kwargs["before"] = discord.Object(id=int(self.anchor))
            else:
                kwargs["after"] = discord.Object(id=int(self.anchor))

            batch = await self._make_api_request(channel, kwargs)
            message_id = None if len(batch) == 0 else getattr(batch[index], "id", None)
            if message_id:
                self.anchor = message_id

            result = batch + result if self.before else result + batch
            if len(batch) < limit or not message_id:
                break

        return result

    async def _make_api_request(self, channel: Any, kwargs: Dict[str, Any]) -> List[Any]:
        """Make a history request

        Args:
            channel: Discord channel object
            kwargs: Keyword arguments

        Returns:
            List of messages
        """
        await self.rate_limiter.limit_request(
            "fetch_history", self.conversation_id
        )

        return [msg async for msg in channel.history(**kwargs)]

    async def _parse_fetched_history(self, history: Any) -> List[Dict[str, Any]]:
        """Parse fetched history

        Args:
            history: List of message history

        Returns:
            List of formatted message history
        """
        formatted_history = []

        for msg in history:
            if self._is_discord_service_message(msg):
                continue
            formatted_history.append(self._format_message(msg))

        return formatted_history

    def _is_discord_service_message(self, message: Any) -> bool:
        """Check if a message is a service message

        Args:
            message: Discord message object

        Returns:
            True if the message is a service message, False otherwise
        """
        return (
            message.type != discord.MessageType.default and
            message.type != discord.MessageType.reply
        )

    def _format_message(self, message: Any) -> Dict[str, Any]:
        """Format a message that is not cached

        Args:
            message: Message to format

        Returns:
            Formatted message
        """
        thread_id = None
        if message.reference and message.reference.message_id:
            thread_id = str(message.reference.message_id)

        formatted_message = {
            "message_id": str(message.id),
            "conversation_id": self.conversation_id,
            "sender": {
                "user_id": str(message.author.id),
                "display_name": message.author.display_name or message.author.name
            },
            "text": message.content,
            "thread_id": thread_id,
            "timestamp": int(message.created_at.timestamp() * 1e3),
            "attachments": []
        }

        return formatted_message
