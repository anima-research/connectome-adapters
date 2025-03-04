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

        self.downloader = Downloader(self.config, self.client)
        self.rate_limiter = RateLimiter.get_instance(self.config)

    async def _fetch_from_api(self,
                              num_before: Optional[int] = None,
                              num_after: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch conversation history

        Returns:
            List of formatted message history
        """
        if not (self.anchor or self.before or self.after):
            return []

        try:
            await self.rate_limiter.limit_request(
                "get_messages", self.conversation.conversation_id
            )

            if self.anchor is None:
                self.anchor = "oldest" if self.after else "newest"
                num_before = self.history_limit * 3 if self.before else 0
                num_after = self.history_limit * 3 if self.after else 0

            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self.client.get_messages({
                    "narrow": json.dumps(self._get_narrow_for_conversation()),
                    "anchor": self.anchor,
                    "num_before": num_before,
                    "num_after": num_after,
                    "include_anchor": False,
                    "apply_markdown": False
                })
            )

            if result.get("result", None) != "success":
                return []

            return await self._parse_fetched_history(result.get("messages", []))
        except Exception as e:
            logging.error(f"Error fetching conversation history: {e}", exc_info=True)
            return []

    def _update_limits(self, cached_messages: List[Dict[str, Any]]) -> None:
        """Update the limits based on the cached messages

        Args:
            cached_messages: List of cached messages
        """
        self.history_limit = self.history_limit - len(cached_messages)

        if not cached_messages:
            return

        if self.before:
            self.anchor = cached_messages[0]["message_id"]
        elif self.after:
            self.anchor = cached_messages[-1]["message_id"]

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

    async def _parse_fetched_history(self, history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Parse fetched history

        Args:
            history: List of message history

        Returns:
            List of formatted message history
        """
        download_tasks = []
        message_map = {}
        attachments = {}

        for i, msg in enumerate(history):
            task = self.downloader.download_attachment(msg)
            download_tasks.append(task)
            message_map[task] = i

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
                "attachments": []
            })

        for task, result in zip(
            download_tasks,
            await asyncio.gather(*download_tasks, return_exceptions=True)
        ):
            if isinstance(result, Exception):
                logging.error(f"Error downloading attachment: {result}")
                continue
            attachments[message_map[task]] = result

        formatted_history = []

        for i, msg in enumerate(history):
            if self.cache_fetched_history:
                delta = await self.conversation_manager.add_to_conversation(
                    {
                        "message": msg,
                        "attachments": attachments.get(i, []),
                        "display_bot_messages": True
                    }
                )
                for cached_msg in delta["added_messages"]:
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

        return self._filter_and_limit_messages(formatted_history)

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
