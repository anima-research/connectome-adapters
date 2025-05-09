import asyncio
import json
import logging
import re

from typing import Any, Dict, List, Optional

from adapters.zulip_adapter.adapter.conversation.manager import Manager
from adapters.zulip_adapter.adapter.attachment_loaders.downloader import Downloader

from core.event_processors.base_history_fetcher import BaseHistoryFetcher
from core.rate_limiter.rate_limiter import RateLimiter
from core.utils.config import Config

class HistoryFetcher(BaseHistoryFetcher):
    """Fetches and formats history from Zulip"""

    def __init__(self,
                 config: Config,
                 client: Any,
                 conversation_manager: Manager,
                 conversation_id: str,
                 anchor: Optional[str] = None,
                 before: Optional[int] = None,
                 after: Optional[int] = None,
                 history_limit: Optional[int] = None):
        """Initialize the ZulipHistoryFetcher

        Args:
            config: Config instance
            client: Zulip client
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
        self.downloader = Downloader(self.config, self.client, False)

    async def _fetch_from_api(self) -> List[Dict[str, Any]]:
        """Fetch conversation history

        Returns:
            List of formatted message history
        """
        if not (self.anchor or self.before or self.after):
            return []

        try:
            result = []

            if self.anchor:
                result = await self._make_api_request(
                    json.dumps(self._get_narrow_for_conversation()),
                    self.history_limit,
                    0
                )
            else:
                if self.before:
                    self.anchor = "newest"
                    result = await self._fetch_history_in_batches(
                        0, self.config.get_setting("adapter", "max_history_limit"), 0
                    )
                elif self.after:
                    self.anchor = "oldest"
                    result = await self._fetch_history_in_batches(
                        -1, 0, self.config.get_setting("adapter", "max_history_limit")
                    )

            return self._filter_and_limit_messages(
                await self._parse_fetched_history(result)
            )
        except Exception as e:
            logging.error(f"Error fetching conversation history: {e}", exc_info=True)
            return []

    async def _fetch_history_in_batches(self,
                                        index: int,
                                        num_before: int,
                                        num_after: int) -> List[Any]:
        """Fetch history in batches

        Args:
            index: Index of the batch
            num_before: Number of messages to fetch before the anchor
            num_after: Number of messages to fetch after the anchor

        Returns:
            List of messages
        """
        narrow = json.dumps(self._get_narrow_for_conversation())
        max_iterations = self.config.get_setting("adapter", "max_pagination_iterations")
        result = []

        for _ in range(max_iterations):
            if len(result) > self.history_limit * 2:
                timestamp_1 = result[0].get("timestamp", 0)
                timestamp_2 = result[-1].get("timestamp", 0)

                if self.before and timestamp_1 < self.before <= timestamp_2:
                    break
                if self.after and timestamp_1 <= self.after < timestamp_2:
                    break

            batch = await self._make_api_request(narrow, num_before, num_after)
            message_id = None if len(batch) == 0 else batch[index].get("id", None)
            if message_id:
                self.anchor = message_id

            result = batch + result if self.before else result + batch
            if len(batch) < num_before:
                break

        return result

    async def _make_api_request(self,
                                narrow: List[Dict[str, Any]],
                                num_before: int,
                                num_after: int) -> List[Any]:
        """Make a history request

        Args:
            narrow: Narrow parameter
            num_before: Number of messages to fetch before the anchor
            num_after: Number of messages to fetch after the anchor

        Returns:
            List of messages
        """
        await self.rate_limiter.limit_request(
            "get_messages", self.conversation.conversation_id
        )

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self.client.get_messages({
                "narrow": narrow,
                "anchor": self.anchor,
                "num_before": num_before,
                "num_after": num_after,
                "include_anchor": False,
                "apply_markdown": False
            })
        )

        if result.get("result", None) != "success":
            return []

        return result.get("messages", [])

    async def _parse_fetched_history(self, history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Parse fetched history

        Args:
            history: List of message history

        Returns:
            List of formatted message history
        """
        formatted_history = []
        attachments = await self._download_attachments(history)

        for i, msg in enumerate(history):
            if self.cache_fetched_history:
                delta = await self.conversation_manager.add_to_conversation(
                    {
                        "message": msg,
                        "attachments": attachments.get(i, []),
                        "display_bot_messages": True
                    }
                )

                for cached_msg in delta.get("added_messages", []):
                    formatted_history.append(cached_msg)
            else:
                formatted_history.append({
                    "message_id": str(msg.get("id", "")),
                    "conversation_id": self.conversation.conversation_id,
                    "sender": {
                        "user_id": str(msg.get("sender_id", "")),
                        "display_name": msg.get("sender_full_name", "")
                    },
                    "text": msg.get("content", ""),
                    "thread_id": self._extract_reply_to_id(msg.get("content", "")),
                    "timestamp": msg.get("timestamp", None),
                    "attachments": attachments.get(i, [])
                })

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

    def _get_narrow_for_conversation(self) -> List[Dict[str, Any]]:
        """Get the narrow parameter for a conversation

        Returns:
            Narrow parameter for API call or empty list if info is not found
        """
        if self.conversation.conversation_type == "private":
            emails = self.conversation.to_fields()
            if emails:
                return [{"operator": "pm-with", "operand": ",".join(emails)}]
            return []

        return [
            {"operator": "stream", "operand": self.conversation.conversation_name},
            {"operator": "topic", "operand": self.conversation.conversation_id.split("/", 1)[1]}
        ]

    def _extract_reply_to_id(self, content: str) -> str:
        """Get the reply to ID from a message

        Args:
            content: The message to extract the reply to ID from

        Returns:
            The reply to ID from the message
        """
        pattern = r'\[said\]\([^\)]+/near/(\d+)\)'
        match = re.search(pattern, content)

        if match:
            return match.group(1)

        return None
