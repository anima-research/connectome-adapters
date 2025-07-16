import asyncio
import emoji
import json
import logging
import os

from pydantic import BaseModel
from typing import Any, Dict, Optional

from src.adapters.discord_adapter.conversation.manager import Manager
from src.adapters.discord_adapter.event_processing.discord_utils import get_discord_channel
from src.adapters.discord_adapter.event_processing.attachment_loaders.uploader import Uploader
from src.adapters.discord_adapter.event_processing.user_info_preprocessor import UserInfoPreprocessor
from src.core.events.processors.base_outgoing_event_processor import BaseOutgoingEventProcessor
from src.core.utils.config import Config

class OutgoingEventProcessor(BaseOutgoingEventProcessor):
    """Processes events from socket.io and sends them to Discord"""

    def __init__(self, config: Config, client: Any, conversation_manager: Manager):
        """Initialize the socket.io events processor

        Args:
            config: Config instance
            client: Discord client instance
            conversation_manager: Conversation manager for tracking message history
        """
        super().__init__(config, client, conversation_manager)
        self.uploader = Uploader(self.config)

    async def _send_message(self, conversation_info: Any, data: BaseModel) -> Dict[str, Any]:
        """Send a message to a chat

        Args:
            conversation_info: Conversation info (not used in this adapter)
            data: Event data containing conversation_id, text, and optional attachments

        Returns:
            Dictionary containing the status and message_ids
        """
        message_ids = []
        channel = await self._get_channel(conversation_info.platform_conversation_id)
        user_info_preprocessor = UserInfoPreprocessor(self.config, self.client)

        for message in self._split_long_message(await user_info_preprocessor.process_outgoing_event(data.mentions, data.text)):
            await self.rate_limiter.limit_request("message", data.conversation_id)
            response = await channel.send(message)
            if hasattr(response, "id"):
                message_ids.append(str(response.id))

        attachment_limit = self.config.get_setting("attachments", "max_attachments_per_message")
        attachments = data.attachments
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

    async def _edit_message(self, conversation_info: Any, data: BaseModel) -> Dict[str, Any]:
        """Edit a message

        Args:
            conversation_info: Conversation info (not used in this adapter)
            data: Event data containing conversation_id, message_id, and text

        Returns:
            Dictionary containing the status
        """
        channel = await self._get_channel(conversation_info.platform_conversation_id)
        message = await channel.fetch_message(int(data.message_id))
        user_info_preprocessor = UserInfoPreprocessor(self.config, self.client)

        await self.rate_limiter.limit_request("edit_message", data.conversation_id)
        await message.edit(content=await user_info_preprocessor.process_outgoing_event(data.mentions, data.text))
        logging.info(f"Message {data.message_id} edited successfully")

        return {"request_completed": True}

    async def _delete_message(self, conversation_info: Any, data: BaseModel) -> Dict[str, Any]:
        """Delete a message

        Args:
            data: Event data containing conversation_id and message_id

        Returns:
            Dictionary containing the status
        """
        channel = await self._get_channel(conversation_info.platform_conversation_id)
        message = await channel.fetch_message(int(data.message_id))

        await self.rate_limiter.limit_request("delete_message", data.conversation_id)
        await message.delete()
        logging.info(f"Message {data.message_id} deleted successfully")

        return {"request_completed": True}

    async def _add_reaction(self, conversation_info: Any, data: BaseModel) -> Dict[str, Any]:
        """Add a reaction to a message

        Args:
            data: Event data containing conversation_id, message_id, and emoji

        Returns:
            Dictionary containing the status
        """
        channel = await self._get_channel(conversation_info.platform_conversation_id)
        message = await channel.fetch_message(int(data.message_id))
        emoji_symbol = emoji.emojize(f":{data.emoji}:")

        if not emoji_symbol or emoji_symbol == f":{data.emoji}:":
            raise Exception(f"Python library emoji does not support this emoji: {data.emoji}")

        await self.rate_limiter.limit_request("add_reaction", data.conversation_id)
        await message.add_reaction(emoji_symbol)
        logging.info(f"Reaction added to message {data.message_id}")
        return {"request_completed": True}

    async def _remove_reaction(self, conversation_info: Any, data: BaseModel) -> Dict[str, Any]:
        """Remove a specific reaction from a message

        Args:
            data: Event data containing conversation_id, message_id, and emoji

        Returns:
            Dictionary containing the status
        """
        channel = await self._get_channel(conversation_info.platform_conversation_id)
        message = await channel.fetch_message(int(data.message_id))
        emoji_symbol = emoji.emojize(f":{data.emoji}:")

        if not emoji_symbol or emoji_symbol == f":{data.emoji}:":
            raise Exception(f"Python library emoji does not support this emoji: {data.emoji}")

        await self.rate_limiter.limit_request("remove_reaction", data.conversation_id)
        await message.remove_reaction(emoji_symbol, self.client.user)
        logging.info(f"Reaction removed from message {data.message_id}")
        return {"request_completed": True}

    async def _pin_message(self, conversation_info: Any, data: BaseModel) -> Dict[str, Any]:
        """Pin a message

        Args:
            data: Event data containing conversation_id and message_id

        Returns:
            Dict[str, Any]: Dictionary containing the status
        """
        channel = await self._get_channel(conversation_info.platform_conversation_id)
        message = await channel.fetch_message(int(data.message_id))

        await self.rate_limiter.limit_request("pin_message", data.conversation_id)
        await message.pin()

        logging.info(f"Message {data.message_id} pinned successfully")
        return {"request_completed": True}

    async def _unpin_message(self, conversation_info: Any, data: BaseModel) -> Dict[str, Any]:
        """Unpin a message

        Args:
            data: Event data containing conversation_id and message_id

        Returns:
            Dict[str, Any]: Dictionary containing the status
        """
        channel = await self._get_channel(conversation_info.platform_conversation_id)
        message = await channel.fetch_message(int(data.message_id))

        await self.rate_limiter.limit_request("unpin_message", data.conversation_id)
        await message.unpin()

        logging.info(f"Message {data.message_id} unpinned successfully")
        return {"request_completed": True}

    async def _get_channel(self, conversation_id: str) -> Optional[Any]:
        """Get a channel from a conversation_id

        Args:
            conversation_id: Conversation ID

        Returns:
            Optional[Any]: Channel object if found, None otherwise
        """
        await self.rate_limiter.limit_request("fetch_channel")

        return await get_discord_channel(self.client, conversation_id)
