import asyncio
import logging
import os

from datetime import datetime
from telethon import functions
from typing import Any, Dict, List, Optional

from adapters.telegram_adapter.adapter.attachment_loaders.downloader import Downloader
from adapters.telegram_adapter.adapter.conversation.manager import Manager

from core.event_processors.base_history_fetcher import BaseHistoryFetcher
from core.rate_limiter.rate_limiter import RateLimiter
from core.utils.config import Config

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
        self.users = {}

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
                "get_history", self.conversation.conversation_id
            )

            result = await self.client(functions.messages.GetHistoryRequest(
                peer=int(self.conversation.conversation_id),
                offset_id=0,
                offset_date=int(self.before / 1000) if self.before else None, # seconds are expected by Telegram API
                add_offset=0,
                limit=self.history_limit * (3 if self.after else 1),
                max_id=0,
                min_id=0,
                hash=0  # This value doesn't matter for most requests
            ))

            if not hasattr(result, "messages") or not result.messages:
                return []

            self._get_users(result)

            if self.cache_fetched_history:
                return await self._parse_and_store_fetched_history(result)
            else:
                return await self._parse_fetched_history(result)
        except Exception as e:
            logging.error(f"Error fetching conversation history: {e}", exc_info=True)
            return []

    def _update_limits(self, cached_messages: List[Dict[str, Any]]) -> None:
        """Update the limits based on the cached messages

        Args:
            cached_messages: List of cached messages
        """
        if not cached_messages:
            return

        if self.before:
            self.before = cached_messages[0]["timestamp"]
        elif self.after:
            self.after = cached_messages[-1]["timestamp"]

        self.history_limit = self.history_limit - len(cached_messages)

    async def _parse_and_store_fetched_history(self, history: Any) -> List[Dict[str, Any]]:
        """Parse fetched history

        Args:
            history: Telegram conversation history

        Returns:
            List of formatted message history
        """
        result = []

        for msg in history.messages:
            attachment_info = []

            if hasattr(msg, 'media') or msg.media:
                attachment_info.append(
                    await self.downloader.download_attachment(
                        msg,
                        self.conversation_manager.attachment_download_required(msg)
                    )
                )

            delta = await self.conversation_manager.add_to_conversation({
                "message": msg,
                "user": self.users.get(self._get_sender_id(msg), None),
                "attachments": attachment_info,
                "display_bot_messages": True
            })

            for message in delta["added_messages"]:
                result.append(message)

        return self._filter_and_limit_messages(result)

    async def _parse_fetched_history(self, history: Any) -> List[Dict[str, Any]]:
        """Parse fetched history

        Args:
            history: Telegram conversation history

        Returns:
            List of formatted message history
        """
        result = []

        for msg in history.messages:
            sender_id = self._get_sender_id(msg)
            sender = self._get_sender_name(sender_id)
            attachment_info = await self._get_attachment_info(msg)

            text = ''
            if hasattr(msg, 'message') and msg.message:
                text = msg.message

            reply_to_msg_id = None
            if hasattr(msg, 'reply_to') and msg.reply_to:
                reply_to_msg_id = getattr(msg.reply_to, 'reply_to_msg_id', None)

            if text or attachment_info:
                result.append({
                    "message_id": str(msg.id),
                    "conversation_id": self.conversation.conversation_id,
                    "sender": {
                        "user_id": str(sender_id) if sender_id else "Unknown",
                        "display_name": sender
                    },
                    "text": text,
                    "thread_id": str(reply_to_msg_id) if reply_to_msg_id else None,
                    "timestamp": int(msg.date.timestamp() * 1e3) if hasattr(msg, 'date') else int(datetime.now().timestamp() * 1e3),
                    "attachments": [attachment_info] if attachment_info else []
                })

        return self._filter_and_limit_messages(result)

    def _get_users(self, history: Any) -> None:
        """Get users from history

        Args:
            history: Telegram conversation history
        """
        if hasattr(history, 'users'):
            for user in getattr(history, 'users', []):
                self.users[user.id] = user

    def _get_sender_id(self, message: Any) -> str:
        """Get sender of a message

        Args:
            message: Telegram message

        Returns:
            Sender id
        """
        if hasattr(message, 'from_id') and message.from_id:
            return getattr(message.from_id, 'user_id', None)
        if hasattr(message, 'peer_id'):
            return getattr(message.peer_id, 'user_id', None)
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
            if hasattr(user, 'username') and user.username:
                sender = f"@{user.username}"
            else:
                sender = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}"

        return sender

    async def _get_attachment_info(self, message: Any) -> Dict[str, Any]:
        """Get attachment info of a message

        Args:
            message: Telegram message

        Returns:
            Attachment info or {}
        """
        if not hasattr(message, 'media') or not message.media:
            return {}

        try:
            metadata = await self.downloader.download_attachment(
                message,
                self.conversation_manager.attachment_download_required(message)
            )

            if not metadata :
                return {}

            if metadata["file_extension"]:
                file_name = f"{metadata['attachment_id']}.{metadata['file_extension']}"
            else:
                file_name = metadata["attachment_id"]

            return {
                "attachment_id": metadata["attachment_id"],
                "attachment_type": metadata["attachment_type"],
                "file_extension": metadata["file_extension"],
                "size": metadata["size"],
                "file_path": os.path.join(
                    self.config.get_setting("attachments", "storage_dir"),
                    metadata["attachment_type"],
                    metadata["attachment_id"],
                    file_name
                )
            }
        except Exception as e:
            logging.warning(f"Error downloading attachment: {e}")
            return {}
