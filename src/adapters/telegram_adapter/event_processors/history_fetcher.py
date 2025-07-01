import asyncio
import logging
import os

from datetime import datetime
from telethon import functions
from typing import Any, Dict, List, Optional

from src.adapters.telegram_adapter.attachment_loaders.downloader import Downloader
from src.adapters.telegram_adapter.conversation.manager import Manager

from src.core.events.history_fetcher.base_history_fetcher import BaseHistoryFetcher
from src.core.rate_limiter.rate_limiter import RateLimiter
from src.core.utils.config import Config

class HistoryFetcher(BaseHistoryFetcher):
    """Formats Telegram history"""

    def __init__(self,
                 config: Config,
                 client: Any,
                 conversation_manager: Manager,
                 conversation_id: str,
                 anchor: Optional[str] = None,
                 before: Optional[int] = None,
                 after: Optional[int] = None,
                 history_limit: Optional[int] = None):
        """Initialize the Telegram HistoryFetcher

        Args:
            config: Config instance
            client: Telethon client
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
        self.users = {}

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
                    self.history_limit, offset_id=0
                )
            elif self.before:
                result = await self._make_api_request(
                    self.history_limit, offset_date=self.before
                )
            elif self.after:
                result = await self._fetch_history_in_batches()

            if result:
                attachments = await self._download_attachments(result)

                if self.cache_fetched_history:
                    result = await self._parse_and_store_fetched_history(result, attachments)
                else:
                    result = await self._parse_fetched_history(result, attachments)

            return self._filter_and_limit_messages(result)
        except Exception as e:
            logging.error(f"Error fetching conversation history: {e}", exc_info=True)
            return []

    async def _fetch_history_in_batches(self) -> List[Any]:
        """Fetch history in batches

        Args:
            channel: Telethon channel object
            index: Index of the batch

        Returns:
            List of messages
        """
        max_iterations = self.config.get_setting("adapter", "max_pagination_iterations")
        limit = self.config.get_setting("adapter", "max_history_limit")
        offset_id = 0
        result = []

        for _ in range(max_iterations):
            if len(result) > self.history_limit * 2:
                timestamp_1 = int(result[0].date.timestamp()) if hasattr(result[0], "date") else 0
                timestamp_2 = int(result[-1].date.timestamp()) if hasattr(result[-1], "date") else 0

                if timestamp_1 <= self.after < timestamp_2:
                    break

            batch = await self._make_api_request(limit, offset_id=offset_id)
            message_id = None if len(batch) == 0 else getattr(batch[-1], "id", None)
            if message_id:
                offset_id = int(message_id)

            result += batch
            if len(batch) < limit or not message_id:
                break

        return result

    async def _make_api_request(self,
                                limit: int,
                                offset_id: Optional[int] = 0,
                                offset_date: Optional[int] = None) -> List[Any]:
        """Make a history request

        Args:
            limit: Limit of messages to fetch
            offset_id: Offset ID
        Returns:
            List of messages
        """
        await self.rate_limiter.limit_request(
            "fetch_history", self.conversation.conversation_id
        )

        if offset_date:
            offset_date = int(offset_date)

        result = await self.client(functions.messages.GetHistoryRequest(
            peer=int(self.conversation.platform_conversation_id),
            offset_id=offset_id,
            offset_date=offset_date,
            add_offset=0,
            limit=limit,
            max_id=0,
            min_id=0,
            hash=0  # This value doesn't matter for most requests
        ))

        if not hasattr(result, "messages") or not result.messages:
            return []

        self._get_users(result)

        return result.messages

    async def _download_attachments(self, messages: Any) -> Dict[Any, Any]:
        """Download attachments

        Args:
            messages: Telegram conversation history

        Returns:
            Dictionary of download results
        """
        download_tasks = []
        message_map = {}
        attachments = {}

        for i, msg in enumerate(messages):
            if hasattr(msg, "media") and msg.media:
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

    async def _parse_and_store_fetched_history(self,
                                               messages: Any,
                                               attachments: Dict[Any, Any]) -> List[Dict[str, Any]]:
        """Parse fetched historyattachments: Dict[Any, Any]

        Args:
            messages: Telegram conversation history
            attachments: Dictionary of download results

        Returns:
            List of formatted message history
        """
        formatted_history = []

        for i, msg in enumerate(messages):
            attachment_info = attachments.get(i, {})
            delta = await self.conversation_manager.add_to_conversation({
                "message": msg,
                "user": self.users.get(self._get_sender_id(msg), None),
                "attachments": [attachment_info] if attachment_info else [],
                "history_fetching_in_progress": True
            })

            for message in delta.get("added_messages", []):
                formatted_history.append(message)

        return formatted_history

    async def _parse_fetched_history(self,
                                     messages: Any,
                                     attachments: Dict[Any, Any]) -> List[Dict[str, Any]]:
        """Parse fetched history

        Args:
            messages: Telegram conversation history
            attachments: Dictionary of download results
        Returns:
            List of formatted message history
        """
        result = []

        for i, msg in enumerate(messages):
            sender_id = self._get_sender_id(msg)
            sender = self._get_sender_name(sender_id)
            attachment_info = self._format_attachment_info(attachments.get(i, {}))

            text = ""
            if hasattr(msg, "message") and msg.message:
                text = msg.message

            reply_to_msg_id = None
            if hasattr(msg, "reply_to") and msg.reply_to:
                reply_to_msg_id = getattr(msg.reply_to, "reply_to_msg_id", None)

            edit_timestamp = None
            if hasattr(msg, "edit_date") and msg.edit_date:
                edit_timestamp = int(msg.edit_date.timestamp())

            if text or attachment_info:
                result.append({
                    "message_id": str(msg.id),
                    "conversation_id": self.conversation.conversation_id,
                    "sender": {
                        "user_id": str(sender_id) if sender_id else "Unknown",
                        "display_name": str(sender) if sender else "Unknown User"
                    },
                    "text": text,
                    "thread_id": str(reply_to_msg_id) if reply_to_msg_id else None,
                    "timestamp": int(msg.date.timestamp()) if hasattr(msg, "date") else int(datetime.now().timestamp()),
                    "edit_timestamp": edit_timestamp,
                    "edited": edit_timestamp is not None,
                    "attachments": [attachment_info] if attachment_info else [],
                    "is_direct_message": self.conversation.conversation_type == "private",
                    "mentions": []
                })

        return result

    def _get_users(self, history: Any) -> None:
        """Get users from history

        Args:
            history: Telegram conversation history
        """
        if hasattr(history, "users"):
            for user in getattr(history, "users", []):
                if user.id not in self.users:
                    self.users[user.id] = user

    def _get_sender_id(self, message: Any) -> str:
        """Get sender of a message

        Args:
            message: Telegram message

        Returns:
            Sender id
        """
        if hasattr(message, "from_id") and message.from_id:
            return getattr(message.from_id, "user_id", None)
        if hasattr(message, "peer_id"):
            return getattr(message.peer_id, "user_id", None)
        return None

    def _get_sender_name(self, sender_id: int) -> str:
        """Get sender name of a message

        Args:
            sender_id: Sender id

        Returns:
            Sender name
        """
        sender = "Unknown User"

        if sender_id in self.users:
            user = self.users.get(sender_id)
            if hasattr(user, "username") and user.username:
                sender = f"@{user.username}"
            else:
                sender = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}"

        return sender

    def _format_attachment_info(self, attachment: Any) -> Dict[str, Any]:
        """Get attachment info of a message

        Args:
            attachment: Telegram attachment

        Returns:
            Attachment info or {}
        """
        if not attachment:
            return {}

        return {
            "attachment_id": attachment["attachment_id"],
            "filename": attachment["filename"],
            "size": attachment["size"],
            "content_type": attachment["content_type"],
            "content": attachment["content"],
            "url": attachment["url"],
            "processable": attachment["processable"]
        }
