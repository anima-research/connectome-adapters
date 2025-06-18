import asyncio
import discord
import logging
import os

from typing import Any, Dict, List, Optional

from src.adapters.discord_adapter.attachment_loaders.downloader import Downloader
from src.adapters.discord_adapter.conversation.manager import Manager
from src.adapters.discord_adapter.event_processors.discord_utils import (
    get_discord_channel, is_discord_service_message
)

from src.core.events.history_fetcher.base_history_fetcher import BaseHistoryFetcher
from src.core.rate_limiter.rate_limiter import RateLimiter
from src.core.utils.config import Config

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
        """Initialize the Discord HistoryFetcher

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

        self.downloader = Downloader(self.config, content_required=False)

    async def _fetch_from_api(self) -> List[Dict[str, Any]]:
        """Fetch conversation history

        Returns:
            List of formatted message history
        """
        if not (self.anchor or self.before or self.after):
            return []

        try:
            channel = await self._get_channel()
            if not channel:
                return []

            result = []
            if self.anchor:
                result = await self._make_api_request(
                    channel, {"limit": self.history_limit}
                )
            elif self.before:
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

        Args:
            channel_id: Channel ID to fetch

        Returns:
            Discord channel object or None if not found
        """
        await self.rate_limiter.limit_request("fetch_channel")

        return await get_discord_channel(
            self.client, self.conversation.conversation_id
        )

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
                timestamp_1 = int(result[0].created_at.timestamp())
                timestamp_2 = int(result[-1].created_at.timestamp())

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
            "fetch_history", self.conversation.conversation_id
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
        attachments = await self._download_attachments(history)

        for i, msg in enumerate(history):
            if is_discord_service_message(msg):
                continue

            if self.cache_fetched_history:
                delta = await self.conversation_manager.add_to_conversation(
                    {
                        "message": msg,
                        "attachments": attachments.get(i, []),
                        "history_fetching_in_progress": True
                    }
                )
                for cached_msg in delta.get("added_messages", []):
                    formatted_history.append(cached_msg)
            else:
                formatted_history.append(
                    self._format_not_cached_message(msg, attachments.get(i, []))
                )

        return formatted_history

    async def _download_attachments(self, history: List[Dict[str, Any]]) -> Dict[Any, Any]:
        """Download attachments

        Args:
            history: List of message history

        Returns:
            Dictionary of download results
        """
        download_tasks = []
        message_map = {}
        attachments = {}

        for i, msg in enumerate(history):
            if not msg.attachments:
                continue
            task = self.downloader.download_attachment(msg)
            download_tasks.append(task)
            message_map[task] = i

        for task, result in zip(
            download_tasks,
            await asyncio.gather(*download_tasks, return_exceptions=True)
        ):
            if isinstance(result, Exception):
                logging.error(f"Error downloading attachment: {result}")
                continue
            attachments[message_map[task]] = result

        return attachments

    def _format_not_cached_message(self,
                                   message: Any,
                                   attachments: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Format a message that is not cached

        Args:
            message: Message to format
            attachments: List of attachments

        Returns:
            Formatted message
        """
        thread_id = None
        if message.reference and message.reference.message_id:
            thread_id = str(message.reference.message_id)

        edit_timestamp = None
        if getattr(message, "edited_at", None) and message.edited_at:
            edit_timestamp = int(message.edited_at.timestamp())

        formatted_message = {
            "message_id": str(message.id),
            "conversation_id": self.conversation.conversation_id,
            "sender": {
                "user_id": str(message.author.id),
                "display_name": message.author.display_name or message.author.name
            },
            "text": message.content,
            "thread_id": thread_id,
            "timestamp": int(message.created_at.timestamp()),
            "edit_timestamp": edit_timestamp,
            "edited": edit_timestamp is not None,
            "attachments": attachments,
            "is_direct_message": self.conversation.conversation_type == "dm",
            "mentions": []
        }

        for attachment in formatted_message["attachments"]:
            for key in ["created_at", "attachment_type"]:
                if key in attachment:
                    del attachment[key]

        return formatted_message
