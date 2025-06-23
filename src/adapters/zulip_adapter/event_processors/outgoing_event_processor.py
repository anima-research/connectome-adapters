import asyncio
import json
import logging
import os

from pydantic import BaseModel
from typing import Any, Dict, List, Optional

from src.adapters.zulip_adapter.attachment_loaders.uploader import Uploader
from src.adapters.zulip_adapter.conversation.manager import Manager

from src.core.conversation.base_data_classes import UserInfo
from src.core.events.processors.base_outgoing_event_processor import BaseOutgoingEventProcessor
from src.core.utils.config import Config
from src.core.utils.emoji_converter import EmojiConverter

class OutgoingEventProcessor(BaseOutgoingEventProcessor):
    """Processes events from socket.io and sends them to Zulip"""

    def __init__(self, config: Config, client: Any, conversation_manager: Manager):
        """Initialize the socket.io events processor

        Args:
            config: Config instance
            client: Zulip client instance
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
            Dict[str, Any]: Dictionary containing the status and message_ids
        """
        messages = self._split_long_message(self._mention_users(conversation_info, data.mentions, data.text))

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
            self._check_api_request_success(result, "send message")

            if "id" in result:
                message_ids.append(str(result["id"]))

        logging.info(f"Message sent to {conversation_info.conversation_id}")
        return {"request_completed": True, "message_ids": message_ids}

    async def _edit_message(self, conversation_info: Any, data: BaseModel) -> Dict[str, Any]:
        """Edit a message

        Args:
            conversation_info: Conversation info
            data: Event data containing conversation_id, message_id, and text

        Returns:
            Dict[str, Any]: Dictionary containing the status
        """
        await self.rate_limiter.limit_request("update_message", data.conversation_id)

        message_data = {
            "message_id": int(data.message_id),
            "content": self._mention_users(conversation_info, data.mentions, data.text)
        }
        self._check_api_request_success(self.client.update_message(message_data), "edit message")

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

        self._check_api_request_success(
            self.client.call_endpoint(
                f"messages/{int(data.message_id)}",
                method="DELETE"
            ),
            "delete message"
        )
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
        self._check_api_request_success(self.client.add_reaction(reaction_data), "add reaction")

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
        self._check_api_request_success(self.client.remove_reaction(reaction_data), "remove reaction")

        logging.info(f"Reaction {data.emoji} removed from message {data.message_id}")
        return {"request_completed": True}

    async def _pin_message(self, data: BaseModel) -> Dict[str, Any]:
        """Pin a message. Not supported for Zulip adapter"""
        raise NotImplementedError("pinning messages is not supported for Zulip adapter")

    async def _unpin_message(self, data: BaseModel) -> Dict[str, Any]:
        """Unpin a message. Not supported for Zulip adapter"""
        raise NotImplementedError("unpinning messages is not supported for Zulip adapter")

    def _conversation_should_exist(self) -> bool:
        """Check if a conversation should exist before sending or editing a message

        Returns:
            bool: True if a conversation should exist, False otherwise

        Note:
            In Zulip the existence of a conversation is mandatory.
        """
        return True

    def _adapter_specific_mention_all(self) -> str:
        """Mention all users in a conversation

        Returns:
            str: Mention all users in a conversation
        """
        return "@**all** "

    def _adapter_specific_mention_user(self, user_info: UserInfo) -> str:
        """Mention a user in a conversation

        Args:
            user_info: User info

        Returns:
            str: Mention a user in a conversation
        """
        return f"@**{user_info.display_name}** "

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
            return

        error_msg = result.get("msg", "Unknown error") if result else "No response"
        raise Exception(f"Failed to {operation}: {error_msg}")
