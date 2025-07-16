import asyncio
import emoji
import json
import logging
import os

from pydantic import BaseModel
from typing import Any, Dict

from src.adapters.slack_adapter.conversation.manager import Manager
from src.adapters.slack_adapter.event_processing.attachment_loaders.uploader import Uploader
from src.adapters.discord_adapter.event_processing.user_info_preprocessor import UserInfoPreprocessor

from src.core.cache.user_cache import UserInfo
from src.core.events.processors.base_outgoing_event_processor import BaseOutgoingEventProcessor
from src.core.utils.config import Config
from src.core.utils.emoji_converter import EmojiConverter

class OutgoingEventProcessor(BaseOutgoingEventProcessor):
    """Processes events from socket.io and sends them to Slack"""

    def __init__(self, config: Config, client: Any, conversation_manager: Manager):
        """Initialize the socket.io events processor

        Args:
            config: Config instance
            client: Slack client instance
            conversation_manager: Conversation manager for tracking message history
        """
        super().__init__(config, client, conversation_manager)
        self.uploader = Uploader(self.config, self.client)

    async def _send_message(self, conversation_info: Any, data: BaseModel) -> Dict[str, Any]:
        """Send a message to a chat

        Args:
            conversation_info: Conversation info
            data: Event data containing conversation_id, text, and optional attachments

        Returns:
            Dictionary containing the status and message_ids
        """
        message_ids = []
        channel_id = conversation_info.platform_conversation_id.split("/")[-1]
        user_info_preprocessor = UserInfoPreprocessor(self.config, self.client)

        for message in self._split_long_message(await user_info_preprocessor.process_outgoing_event(data.mentions, data.text)):
            await self.rate_limiter.limit_request("message", data.conversation_id)

            message_params = {
                "channel": channel_id,
                "text": message,
                "unfurl_links": False,
                "unfurl_media": False
            }
            if data.thread_id:
                message_params["thread_ts"] = data.thread_id

            response = await self.client.chat_postMessage(**message_params)
            if response.get("ok", None):
                message_id = response.get("ts", None)
                if message_id:
                    message_ids.append(message_id)
            else:
                raise Exception(f"Failed to send message: {response['error']}")

        await self.uploader.upload_attachments(conversation_info, data)

        logging.info(f"Message sent to {data.conversation_id} with attachments")
        return {"request_completed": True, "message_ids": message_ids}

    async def _edit_message(self, conversation_info: Any, data: BaseModel) -> Dict[str, Any]:
        """Edit a message

        Args:
            conversation_info: Conversation info
            data: Event data containing conversation_id, message_id, and text

        Returns:
            Dictionary containing the status
        """
        channel_id = conversation_info.platform_conversation_id.split("/")[-1]
        user_info_preprocessor = UserInfoPreprocessor(self.config, self.client)

        await self.rate_limiter.limit_request("edit_message", data.conversation_id)
        response = await self.client.chat_update(
            channel=channel_id,
            ts=data.message_id,
            text=await user_info_preprocessor.process_outgoing_event(data.mentions, data.text)
        )

        if not response.get("ok", None):
            raise Exception(f"Failed to send message: {response['error']}")

        logging.info(f"Message {data.message_id} edited successfully")

        return {"request_completed": True}

    async def _delete_message(self, conversation_info: Any, data: BaseModel) -> Dict[str, Any]:
        """Delete a message

        Args:
            conversation_info: Conversation info
            data: Event data containing conversation_id and message_id

        Returns:
            Dictionary containing the status
        """
        channel_id = conversation_info.platform_conversation_id.split("/")[-1]

        await self.rate_limiter.limit_request("delete_message", data.conversation_id)
        response = await self.client.chat_delete(
            channel=channel_id,
            ts=data.message_id
        )

        if not response.get("ok", None):
            raise Exception(f"Failed to delete message: {response['error']}")

        logging.info(f"Message {data.message_id} deleted successfully")

        return {"request_completed": True}

    async def _add_reaction(self, conversation_info: Any, data: BaseModel) -> Dict[str, Any]:
        """Add a reaction to a message

        Args:
            conversation_info: Conversation info
            data: Event data containing conversation_id, message_id, and emoji

        Returns:
            Dictionary containing the status
        """
        channel_id = conversation_info.platform_conversation_id.split("/")[-1]

        await self.rate_limiter.limit_request("add_reaction", data.conversation_id)
        response = await self.client.reactions_add(
            channel=channel_id,
            timestamp=data.message_id,
            name=EmojiConverter.get_instance().standard_to_platform_specific(data.emoji)
        )

        if not response.get("ok", None):
            raise Exception(f"Failed to add reaction: {response['error']}")

        logging.info(f"Reaction added to message {data.message_id}")

        return {"request_completed": True}

    async def _remove_reaction(self, conversation_info: Any, data: BaseModel) -> Dict[str, Any]:
        """Remove a specific reaction from a message

        Args:
            conversation_info: Conversation info
            data: Event data containing conversation_id, message_id, and emoji

        Returns:
            Dictionary containing the status
        """
        channel_id = conversation_info.platform_conversation_id.split("/")[-1]

        await self.rate_limiter.limit_request("remove_reaction", data.conversation_id)
        response = await self.client.reactions_remove(
            channel=channel_id,
            timestamp=data.message_id,
            name=EmojiConverter.get_instance().standard_to_platform_specific(data.emoji)
        )

        if not response.get("ok", None):
            raise Exception(f"Failed to add reaction: {response['error']}")

        logging.info(f"Reaction removed from message {data.message_id}")

        return {"request_completed": True}

    async def _pin_message(self, conversation_info: Any, data: BaseModel) -> Dict[str, Any]:
        """Pin a message

        Args:
            conversation_info: Conversation info
            data: Event data containing conversation_id and message_id

        Returns:
            Dict[str, Any]: Dictionary containing the status
        """
        channel_id = conversation_info.platform_conversation_id.split("/")[-1]

        await self.rate_limiter.limit_request("pin_message", data.conversation_id)
        response = await self.client.pins_add(channel=channel_id, timestamp=data.message_id)

        if not response.get("ok", None):
            raise Exception(f"Failed to pin message: {response['error']}")

        logging.info(f"Message {data.message_id} pinned successfully")

        return {"request_completed": True}

    async def _unpin_message(self, conversation_info: Any, data: BaseModel) -> Dict[str, Any]:
        """Unpin a message

        Args:
            conversation_info: Conversation info
            data: Event data containing conversation_id and message_id

        Returns:
            Dict[str, Any]: Dictionary containing the status
        """
        channel_id = conversation_info.platform_conversation_id.split("/")[-1]

        await self.rate_limiter.limit_request("unpin_message", data.conversation_id)
        response = await self.client.pins_remove(channel=channel_id, timestamp=data.message_id)

        if not response.get("ok", None):
            raise Exception(f"Failed to unpin message: {response['error']}")

        logging.info(f"Message {data.message_id} unpinned successfully")

        return {"request_completed": True}
