import asyncio
import logging
import os

from typing import Any, Dict, List, Optional

from adapters.slack_adapter.adapter.attachment_loaders.downloader import Downloader
from adapters.slack_adapter.adapter.conversation.manager import Manager

from core.event_processors.base_history_fetcher import BaseHistoryFetcher
from core.utils.config import Config

class HistoryFetcher(BaseHistoryFetcher):
    """Fetches and formats history from Slack"""

    def __init__(self,
                 config: Config,
                 client: Any,
                 conversation_manager: Manager,
                 conversation_id: str,
                 anchor: Optional[str] = None,
                 before: Optional[int] = None,
                 after: Optional[int] = None,
                 history_limit: Optional[int] = None):
        """Initialize the SlackHistoryFetcher

        Args:
            config: Config instance
            client: Slack client
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
        self.users = {}

    async def _fetch_from_api(self) -> List[Dict[str, Any]]:
        """Fetch conversation history

        Returns:
            List of formatted message history
        """
        if not (self.anchor or self.before or self.after):
            return []

        try:
            channel_id = self.conversation.conversation_id.split("/")[-1]
            params = {"channel": channel_id, "inclusive": False}

            if self.anchor:
                params["latest"] = self.anchor
            elif self.before:
                params["latest"] = f"{int(self.before / 1e3):.6f}"
            elif self.after:
                params["oldest"] = f"{int(self.after / 1e3):.6f}"

            result = await self._fetch_history_in_batches(params)

            return self._filter_and_limit_messages(
                await self._parse_fetched_history(result)
            )
        except Exception as e:
            logging.error(f"Error fetching conversation history: {e}", exc_info=True)
            return []

    async def _fetch_history_in_batches(self, params: Dict[str, Any]) -> List[Any]:
        """Fetch history in batches

        Args:
            params: Dictionary of parameters

        Returns:
            List of messages
        """
        default_limit = self.config.get_setting("adapter", "max_history_limit")
        limit_to_use = default_limit

        if self.history_limit and self.history_limit < limit_to_use:
            limit_to_use = self.history_limit

        params["limit"] = limit_to_use
        count = 0
        result = []

        while count < self.history_limit:
            await self.rate_limiter.limit_request(
                "fetch_history", self.conversation.conversation_id
            )

            response = await self.client.conversations_history(**params)
            if not response.get("ok", False):
                logging.error(
                    f"Error fetching conversation history: {response.get('error')}",
                    exc_info=True
                )
                break

            batch = response.get("messages", [])
            if not batch:
                break
            result += batch

            if self.anchor or self.before:
                params["latest"] = batch[-1]["ts"]
            elif self.after:
                params["oldest"] = batch[0]["ts"]

            count += limit_to_use

        return result

    async def _parse_fetched_history(self, history: Any) -> List[Dict[str, Any]]:
        """Parse fetched history

        Args:
            history: List of message history

        Returns:
            List of formatted message history
        """
        formatted_history = []
        attachments = await self._download_attachments(history)

        if self.cache_fetched_history:
            for i, msg in enumerate(history):
                msg["conversation_id"] = self.conversation.conversation_id
                delta = await self.conversation_manager.add_to_conversation(
                    {
                        "message": msg,
                        "user": await self._get_user_info(msg),
                        "attachments": attachments.get(i, []),
                        "display_bot_messages": True
                    }
                )

                for cached_msg in delta["added_messages"]:
                    formatted_history.append(cached_msg)
        else:
            for i, msg in enumerate(history):
                formatted_history.append(
                    self._format_not_cached_message(
                        msg, attachments.get(i, []), await self._get_user_info(msg)
                    )
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
            if not msg.get("files", []):
                continue
            task = self.downloader.download_attachments(msg)
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
                                   message: Dict[str, Any],
                                   attachments: List[Dict[str, Any]],
                                   user_info: Optional[Dict[str, Any]] = {}) -> Dict[str, Any]:
        """Format a message that is not cached

        Args:
            message: Message to format
            attachments: List of attachments

        Returns:
            Formatted message
        """
        return {
            "message_id": message.get("ts", None),
            "conversation_id": self.conversation.conversation_id,
            "sender": {
                "user_id": str(message.get("user", "")),
                "display_name": str(user_info.get("name", "Unknown user"))
            },
            "text": message.get("text", ""),
            "thread_id": message.get("thread_ts", None),
            "timestamp": int(float(message.get("ts", "0")) * 1e3),
            "attachments": attachments
        }

    async def _get_user_info(self, message: Any) -> Optional[Dict[str, Any]]:
        """Get user info

        Args:
            message: Message

        Returns:
            User info dictionary
        """
        user_id = str(message.get("user", ""))

        if not user_id:
            return {}
        if user_id in self.users:
            return self.users[user_id]

        await self.rate_limiter.limit_request("get_user_info")
        user_info = await self.client.users_info(user=user_id)

        if user_info and "user" in user_info:
            self.users[user_id] = user_info["user"]
            return self.users[user_id]

        return {}
