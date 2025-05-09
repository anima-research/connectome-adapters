import asyncio
import emoji
import json
import logging
import os

from pydantic import BaseModel
from typing import Dict, Any, Optional

from adapters.discord_adapter.adapter.attachment_loaders.uploader import Uploader
from adapters.discord_adapter.adapter.conversation.manager import Manager
from adapters.discord_adapter.adapter.event_processors.discord_utils import get_discord_channel
from adapters.discord_adapter.adapter.event_processors.history_fetcher import HistoryFetcher

from core.event_processors.base_outgoing_event_processor import BaseOutgoingEventProcessor
from core.utils.config import Config

class OutgoingEventProcessor(BaseOutgoingEventProcessor):
    """Processes events from socket.io and sends them to Discord"""

    def __init__(self, config: Config, client: Any, conversation_manager: Manager):
        """Initialize the socket.io events processor

        Args:
            config: Config instance
            client: Discord client instance
            conversation_manager: Conversation manager for tracking message history
        """
        super().__init__(config, client)
        self.conversation_manager = conversation_manager
        self.uploader = Uploader(self.config)

    async def _send_message(self, data: BaseModel) -> Dict[str, Any]:
        """Send a message to a chat

        Args:
            data: Event data containing conversation_id, text, and optional attachments

        Returns:
            Dictionary containing the status and message_ids
        """
        message_ids = []
        channel = await self._get_channel(data.conversation_id)

        for message in self._split_long_message(data.text):
            await self.rate_limiter.limit_request("message", data.conversation_id)
            response = await channel.send(message)
            if hasattr(response, "id"):
                message_ids.append(str(response.id))

        attachments = data.attachments
        attachment_limit = self.config.get_setting(
            "attachments", "max_attachments_per_message"
        )

        if attachments:
            attachment_chunks = [
                attachments[i:i+attachment_limit]
                for i in range(0, len(attachments), attachment_limit)
            ]
            clean_up_paths = []

            for chunk in attachment_chunks:
                await self.rate_limiter.limit_request("message", data.conversation_id)
                files, paths = self.uploader.upload_attachment(chunk)
                clean_up_paths.extend(paths)
                response = await channel.send(files=files)
                if hasattr(response, "id"):
                    message_ids.append(str(response.id))
            self.uploader.clean_up_uploaded_files(clean_up_paths)

        logging.info(f"Message sent to {data.conversation_id} with {len(attachments)} attachments")
        return {"request_completed": True, "message_ids": message_ids}

    async def _edit_message(self, data: BaseModel) -> Dict[str, Any]:
        """Edit a message

        Args:
            data: Event data containing conversation_id, message_id, and text

        Returns:
            Dictionary containing the status
        """
        channel = await self._get_channel(data.conversation_id)
        message = await channel.fetch_message(int(data.message_id))

        await self.rate_limiter.limit_request("edit_message", data.conversation_id)
        await message.edit(content=data.text)
        logging.info(f"Message {data.message_id} edited successfully")

        return {"request_completed": True}

    async def _delete_message(self, data: BaseModel) -> Dict[str, Any]:
        """Delete a message

        Args:
            data: Event data containing conversation_id and message_id

        Returns:
            Dictionary containing the status
        """
        channel = await self._get_channel(data.conversation_id)
        message = await channel.fetch_message(int(data.message_id))

        await self.rate_limiter.limit_request("delete_message", data.conversation_id)
        await message.delete()
        logging.info(f"Message {data.message_id} deleted successfully")

        return {"request_completed": True}

    async def _add_reaction(self, data: BaseModel) -> Dict[str, Any]:
        """Add a reaction to a message

        Args:
            data: Event data containing conversation_id, message_id, and emoji

        Returns:
            Dictionary containing the status
        """
        channel = await self._get_channel(data.conversation_id)
        message = await channel.fetch_message(int(data.message_id))
        emoji_symbol = emoji.emojize(f":{data.emoji}:")

        if not emoji_symbol or emoji_symbol == f":{data.emoji}:":
            logging.error(f"Python library emoji does not support this emoji: {data.emoji}")
            return {"request_completed": False}

        await self.rate_limiter.limit_request("add_reaction", data.conversation_id)
        await message.add_reaction(emoji_symbol)
        logging.info(f"Reaction added to message {data.message_id}")
        return {"request_completed": True}

    async def _remove_reaction(self, data: BaseModel) -> Dict[str, Any]:
        """Remove a specific reaction from a message

        Args:
            data: Event data containing conversation_id, message_id, and emoji

        Returns:
            Dictionary containing the status
        """
        channel = await self._get_channel(data.conversation_id)
        message = await channel.fetch_message(int(data.message_id))
        emoji_symbol = emoji.emojize(f":{data.emoji}:")

        if not emoji_symbol or emoji_symbol == f":{data.emoji}:":
            logging.error(f"Python library emoji does not support this emoji: {data.emoji}")
            return {"request_completed": False}

        await self.rate_limiter.limit_request("remove_reaction", data.conversation_id)
        await message.remove_reaction(emoji_symbol, self.client.user)
        logging.info(f"Reaction removed from message {data.message_id}")
        return {"request_completed": True}

    async def _fetch_history(self, data: BaseModel) -> Dict[str, Any]:
        """Fetch history of a conversation

        Args:
            data: Event data containing conversation_id,
                  before or after datetime as int (one of the two must be provided),
                  limit (optional, default is taken from config)

        Returns:
            Dict[str, Any]: Dictionary containing the status and history
        """
        if not data.before and not data.after:
            logging.error("No before or after datetime provided")
            return {"request_completed": False}

        history = await HistoryFetcher(
            self.config,
            self.client,
            self.conversation_manager,
            data.conversation_id,
            before=data.before,
            after=data.after,
            history_limit=data.limit
        ).fetch()

        return {"request_completed": True, "history": history}

    async def _get_channel(self, conversation_id: str) -> Optional[Any]:
        """Get a channel from a conversation_id

        Args:
            conversation_id: Conversation ID

        Returns:
            Optional[Any]: Channel object if found, None otherwise
        """
        await self.rate_limiter.limit_request("fetch_channel")

        return await get_discord_channel(self.client, conversation_id)
