import aiohttp
import asyncio
import json
import logging

from pydantic import BaseModel
from typing import Any, Dict, List

from adapters.discord_webhook_adapter.adapter.attachment_loaders.uploader import Uploader
from adapters.discord_webhook_adapter.adapter.conversation.manager import Manager

from adapters.discord_webhook_adapter.adapter.event_processors.history_fetcher import HistoryFetcher
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
        self.session = self.client.session
        self.conversation_manager = conversation_manager
        self.uploader = Uploader(self.config)

    async def _send_message(self, data: BaseModel) -> Dict[str, Any]:
        """Send a message to a chat

        Args:
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

        self.uploader.clean_up_uploaded_files(data.attachments)
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

    async def _edit_message(self, data: BaseModel) -> Dict[str, Any]:
        """Edit a message

        Args:
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

    async def _delete_message(self, data: BaseModel) -> Dict[str, Any]:
        """Delete a message

        Args:
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

        webhook_info = await self._get_webhook_info(data.conversation_id)
        history = await HistoryFetcher(
            self.config,
            self.client.get_client_bot(webhook_info["bot_token"]),
            self.conversation_manager,
            data.conversation_id,
            before=data.before,
            after=data.after,
            history_limit=data.limit
        ).fetch()

        return {"request_completed": True, "history": history}

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
        if response.status < 400:
            return
        raise Exception(f"Error processing webhook message: {await response.text()}")

    async def _add_reaction(self, data: BaseModel) -> Dict[str, Any]:
        """Add a reaction to a message. Not supported for webhooks adapter"""
        raise NotImplementedError("adding reactions is not supported for webhooks adapter")

    async def _remove_reaction(self, data: BaseModel) -> Dict[str, Any]:
        """Remove a reaction from a message. Not supported for webhooks adapter"""
        raise NotImplementedError("removing reactions is not supported for webhooks adapter")
