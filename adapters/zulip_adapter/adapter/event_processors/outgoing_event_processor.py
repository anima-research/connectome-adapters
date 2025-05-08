import asyncio
import json
import logging
import os

from pydantic import BaseModel
from typing import Any, Dict, Optional

from adapters.zulip_adapter.adapter.attachment_loaders.uploader import Uploader
from adapters.zulip_adapter.adapter.conversation.manager import Manager
from adapters.zulip_adapter.adapter.event_processors.history_fetcher import HistoryFetcher

from core.event_processors.base_outgoing_event_processor import BaseOutgoingEventProcessor
from core.utils.config import Config
from core.utils.emoji_converter import EmojiConverter

class OutgoingEventProcessor(BaseOutgoingEventProcessor):
    """Processes events from socket.io and sends them to Zulip"""

    def __init__(self, config: Config, client: Any, conversation_manager: Manager):
        """Initialize the socket.io events processor

        Args:
            config: Config instance
            client: Zulip client instance
            conversation_manager: Conversation manager for tracking message history
        """
        super().__init__(config, client)
        self.conversation_manager = conversation_manager
        self.uploader = Uploader(self.config, self.client)

    async def _send_message(self, data: BaseModel) -> Dict[str, Any]:
        """Send a message to a chat

        Args:
            data: Event data containing conversation_id, text, and optional attachments

        Returns:
            Dict[str, Any]: Dictionary containing the status and message_ids
        """
        conversation_info = self.conversation_manager.get_conversation(data.conversation_id)
        if not conversation_info:
            logging.error(f"Conversation {data.conversation_id} not found")
            return {"request_completed": False}

        messages = self._split_long_message(data.text)
        for attachment in data.attachments:
            await self.rate_limiter.limit_request("upload_attachment", conversation_info.conversation_id)
            uri = await self.uploader.upload_attachment(attachment)
            file_name = uri.split("/")[-1]
            messages[-1] += f"\n[{file_name}]({uri})"

        to_field = conversation_info.to_fields()
        message_type = conversation_info.conversation_type
        subject = None

        if conversation_info.conversation_type == "stream":
            subject = conversation_info.conversation_id.split("/")[1]

        message_ids = []
        for message in messages:
            await self.rate_limiter.limit_request("message", conversation_info.conversation_id)
            result = self.client.send_message({
                "type": message_type,
                "to": to_field,
                "content": message,
                "subject": subject
            })

            if not self._check_api_request_success(
                result, f"send message to {conversation_info.conversation_id}"
            ):
                return {"request_completed": False}

            if "id" in result:
                message_ids.append(str(result["id"]))

        logging.info(f"Message sent to {conversation_info.conversation_id}")
        return {"request_completed": True, "message_ids": message_ids}

    async def _edit_message(self, data: BaseModel) -> Dict[str, Any]:
        """Edit a message

        Args:
            data: Event data containing conversation_id, message_id, and text

        Returns:
            Dict[str, Any]: Dictionary containing the status
        """
        await self.rate_limiter.limit_request("update_message", data.conversation_id)

        message_data = {
            "message_id": int(data.message_id),
            "content": data.text
        }

        if not self._check_api_request_success(
            self.client.update_message(message_data),
            f"edit message {data.message_id}"
        ):
            return {"request_completed": False}

        logging.info(f"Message {data.message_id} edited successfully")
        return {"request_completed": True}

    async def _delete_message(self, data: BaseModel) -> Dict[str, Any]:
        """Delete a message

        Args:
            data: Event data containing conversation_id and message_id

        Returns:
            Dict[str, Any]: Dictionary containing the status
        """
        await self.rate_limiter.limit_request("delete_message", data.conversation_id)

        if not self._check_api_request_success(
            self.client.call_endpoint(
                f"messages/{int(data.message_id)}",
                method="DELETE"
            ),
            f"delete message {data.message_id}"
        ):
            return {"request_completed": False}

        await self.conversation_manager.delete_from_conversation(
            outgoing_event={
                "message_id": data.message_id,
                "conversation_id": data.conversation_id
            }
        )

        logging.info(f"Message {data.message_id} deleted successfully")
        return {"request_completed": True}

    async def _add_reaction(self, data: BaseModel) -> Dict[str, Any]:
        """Add a reaction to a message

        Args:
            data: Event data containing conversation_id, message_id, and emoji

        Returns:
            Dict[str, Any]: Dictionary containing the status
        """
        await self.rate_limiter.limit_request("add_reaction", data.conversation_id)

        reaction_data = {
            "message_id": int(data.message_id),
            "emoji_name": EmojiConverter.get_instance().standard_to_platform_specific(data.emoji)
        }

        if not self._check_api_request_success(
            self.client.add_reaction(reaction_data),
            f"add reaction to {data.message_id}"
        ):
            return {"request_completed": False}

        logging.info(f"Reaction {data.emoji} added to message {data.message_id}")
        return {"request_completed": True}

    async def _remove_reaction(self, data: BaseModel) -> Dict[str, Any]:
        """Remove a specific reaction from a message

        Args:
            data: Event data containing conversation_id, message_id, and emoji

        Returns:
            Dict[str, Any]: Dictionary containing the status
        """
        await self.rate_limiter.limit_request("remove_reaction", data.conversation_id)

        reaction_data = {
            "message_id": int(data.message_id),
            "emoji_name": EmojiConverter.get_instance().standard_to_platform_specific(data.emoji)
        }

        if not self._check_api_request_success(
            self.client.remove_reaction(reaction_data),
            f"remove reaction from {data.message_id}"
        ):
            return {"request_completed": False}

        logging.info(f"Reaction {data.emoji} removed from message {data.message_id}")
        return {"request_completed": True}

    async def _fetch_history(self, data: BaseModel) -> Dict[str, Any]:
        """Fetch history of a conversation

        Args:
            data: Event data containing conversation_id, before or after datetime as int (one of the two must be provided),
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

    def _check_api_request_success(self,
                                   result: Optional[Dict[str, Any]],
                                   operation: str) -> bool:
        """Check if a Zulip API result was successful

        Args:
            result: API response dictionary
            operation: Description of operation for logging

        Returns:
            bool: True if successful, False otherwise
        """
        if result and result.get("result", None) == "success":
            return True

        error_msg = result.get("msg", "Unknown error") if result else "No response"
        logging.error(f"Failed to {operation}: {error_msg}")
        return False
