import aiohttp
import asyncio
import json
import logging

from pydantic import BaseModel
from typing import Any, Dict, List

from src.adapters.discord_webhook_adapter.event_processing.attachment_loaders.uploader import Uploader
from src.adapters.discord_webhook_adapter.conversation.manager import Manager

from src.core.conversation.base_data_classes import UserInfo
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
        self.session = self.client.session
        self.uploader = Uploader(self.config)

    async def _handle_fetch_attachment_event(self, data: BaseModel) -> Dict[str, Any]:
        """Fetch attachment event is not available for webhooks adapter.
        We do not cache messages and attachments for webhooks adapter, therefore
        we cannot fetch anything on demand.
        """
        raise NotImplementedError("Fetching attachments is not available for webhooks adapter")

    async def _send_message(self, _: Any, data: BaseModel) -> Dict[str, Any]:
        """Send a message to a chat

        Args:
            conversation_info: Conversation info (not used in this adapter)
            data: Event data containing conversation_id, text, and optional attachments

        Returns:
            Dictionary containing the status and message_ids
        """
        webhook_info = await self._get_webhook_info(data.conversation_id)
        webhook_info["conversation_id"] = data.conversation_id

        if data.custom_name:
            webhook_info["name"] = data.custom_name

        message_ids = []

        for response in await self._send_text_message(webhook_info, data.text):
            message_ids.append(response.get("id", ""))
            self.conversation_manager.add_to_conversation({**response, **webhook_info})

        attachments = self.uploader.upload_attachment(data.attachments)
        for response in await self._send_attachments(webhook_info, attachments):
            message_ids.append(response.get("id", ""))
            self.conversation_manager.add_to_conversation({**response, **webhook_info})

        self.uploader.clean_up_uploaded_files(attachments)
        logging.info(f"Message sent to {data.conversation_id}")
        return {"request_completed": True, "message_ids": list(filter(len, message_ids))}

    async def _send_text_message(self,
                                 webhook_info: Dict[str, Any],
                                 initial_message: str) -> List[Any]:
        """Send a text message to a webhook

        Args:
            webhook_info: Webhook information
            message: Message to send

        Returns:
            List[Any]: API responses
        """
        responses = []

        for message in self._split_long_message(initial_message):
            await self.rate_limiter.limit_request("message", webhook_info["url"])
            response = await self.session.post(
                webhook_info["url"] + "?wait=true",
                json={"content": message, "username": webhook_info["name"]}
            )
            await self._check_api_response(response)
            responses.append(await response.json())

        return responses

    async def _send_attachments(self,
                                webhook_info: Dict[str, Any],
                                attachments: List[Any]) -> List[Any]:
        """Send attachments to a webhook

        Args:
            webhook_info: Webhook information
            attachments: Attachments to send

        Returns:
            List[Any]: API responses
        """
        attachment_limit = self.config.get_setting(
            "attachments", "max_attachments_per_message"
        )
        attachment_chunks = [
            attachments[i:i+attachment_limit]
            for i in range(0, len(attachments), attachment_limit)
        ] if attachments else []
        payload = {"content": "", "username": webhook_info["name"]}
        responses = []

        for chunk in attachment_chunks:
            await self.rate_limiter.limit_request("message", webhook_info["url"])
            form = aiohttp.FormData()
            for i, attachment in enumerate(chunk):
                with open(attachment, "rb") as f:
                    filename = attachment.split("/")[-1]
                    form.add_field(f"file{i}", f.read(), filename=filename)
            form.add_field("payload_json", json.dumps(payload))
            response = await self.session.post(
                webhook_info["url"] + "?wait=true", data=form
            )
            await self._check_api_response(response)
            responses.append(await response.json())

        return responses

    async def _edit_message(self, _: Any, data: BaseModel) -> Dict[str, Any]:
        """Edit a message

        Args:
            conversation_info: Conversation info (not used in this adapter)
            data: Event data containing conversation_id, message_id, and text

        Returns:
            Dictionary containing the status
        """
        webhook_info = await self._get_webhook_info(data.conversation_id)
        await self.rate_limiter.limit_request("edit_message", webhook_info["url"])
        await self._check_api_response(
            await self.session.patch(
                f"{webhook_info['url']}/messages/{data.message_id}",
                json={"content": data.text}
            )
        )
        logging.info(f"Message {data.message_id} edited successfully")
        return {"request_completed": True}

    async def _delete_message(self, _: Any, data: BaseModel) -> Dict[str, Any]:
        """Delete a message

        Args:
            conversation_info: Conversation info (not used in this adapter)
            data: Event data containing conversation_id and message_id

        Returns:
            Dictionary containing the status
        """
        webhook_info = await self._get_webhook_info(data.conversation_id)
        await self.rate_limiter.limit_request("delete_message", webhook_info["url"])
        await self._check_api_response(
            await self.session.delete(
                f"{webhook_info['url']}/messages/{data.message_id}"
            )
        )
        self.conversation_manager.delete_from_conversation({
            "conversation_id": data.conversation_id,
            "message_id": data.message_id
        })
        logging.info(f"Message {data.message_id} deleted successfully")
        return {"request_completed": True}

    async def _get_webhook_info(self, conversation_id: str) -> Dict[str, Any]:
        """Get webhook info for a conversation

        Args:
            conversation_id: Conversation ID

        Returns:
            Dict[str, Any]: Webhook info
        """
        webhook_info = await self.client.get_or_create_webhook(conversation_id)
        if webhook_info:
            return webhook_info.copy()
        raise Exception(f"No webhook configured for conversation {conversation_id}")

    async def _check_api_response(self, response: Any) -> None:
        """Check the API response for errors"""
        if response.status >= 400:
            raise Exception(f"Error processing webhook message: {await response.text()}")

    async def _handle_fetch_history_event(self, data: BaseModel) -> Dict[str, Any]:
        """Fetch history of a conversation. Not supported for webhooks adapter"""
        raise NotImplementedError("fetching history is not supported for webhooks adapter")

    async def _add_reaction(self, _: Any, data: BaseModel) -> Dict[str, Any]:
        """Add a reaction to a message. Not supported for webhooks adapter"""
        raise NotImplementedError("adding reactions is not supported for webhooks adapter")

    async def _remove_reaction(self, _: Any, data: BaseModel) -> Dict[str, Any]:
        """Remove a reaction from a message. Not supported for webhooks adapter"""
        raise NotImplementedError("removing reactions is not supported for webhooks adapter")

    async def _pin_message(self, _: Any, data: BaseModel) -> Dict[str, Any]:
        """Pin a message. Not supported for webhooks adapter"""
        raise NotImplementedError("pinning messages is not supported for webhooks adapter")

    async def _unpin_message(self, _: Any, data: BaseModel) -> Dict[str, Any]:
        """Unpin a message. Not supported for webhooks adapter"""
        raise NotImplementedError("unpinning messages is not supported for webhooks adapter")

    def _find_conversation(self, _: str) -> Any:
        """Find a conversation by id

        Returns:
            None because we do not need to find a conversation for webhooks adapter
        """
        return None
