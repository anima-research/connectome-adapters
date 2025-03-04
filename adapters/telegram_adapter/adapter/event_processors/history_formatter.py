import asyncio
import logging
import os

from datetime import datetime
from typing import List, Dict, Any

from adapters.telegram_adapter.adapter.attachment_loaders.downloader import Downloader
from adapters.telegram_adapter.adapter.conversation.manager import Manager

from core.rate_limiter.rate_limiter import RateLimiter
from core.utils.config import Config

class HistoryFormatter:
    """Formats Telegram history"""

    def __init__(self,
                 config: Config,
                 downloader: Downloader,
                 conversation_manager: Manager,
                 history: List[Dict[str, Any]],
                 conversation_id: str):
        self.config = config
        self.downloader = downloader
        self.conversation_manager = conversation_manager
        self.history = history
        self.users = {}
        self.conversation_id = conversation_id
        self.rate_limiter = RateLimiter.get_instance(self.config)

        self._get_users()

    def _get_users(self) -> None:
        """Get users from history"""
        if hasattr(self.history, 'users'):
            for user in getattr(self.history, 'users', []):
                self.users[user.id] = user

    async def format_history(self) -> List[Dict[str, Any]]:
        """Format Telegram history

        Returns:
            List of formatted messages
        """
        if not hasattr(self.history, "messages") or not self.history.messages:
            return []

        result = []

        for msg in self.history.messages:
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
                    "conversation_id": self.conversation_id,
                    "sender": {
                        "user_id": str(sender_id) if sender_id else "Unknown",
                        "display_name": sender
                    },
                    "text": text,
                    "thread_id": str(reply_to_msg_id) if reply_to_msg_id else None,
                    "timestamp": int(msg.date.timestamp() * 1e3) if hasattr(msg, 'date') else int(datetime.now().timestamp() * 1e3),
                    "attachments": [attachment_info] if attachment_info else []
                })

        return list(reversed(result))

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

            if not metadata:
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
