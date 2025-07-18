import asyncio
import base64
import emoji
import json
import logging
import os

from abc import ABC, abstractmethod
from enum import Enum
from pydantic import BaseModel
from typing import Any, Dict, List

from src.core.cache.cache import Cache
from src.core.conversation.base_data_classes import BaseConversationInfo, UserInfo
from src.core.events.builders.outgoing_event_builder import OutgoingEventBuilder
from src.core.rate_limiter.rate_limiter import RateLimiter
from src.core.utils.config import Config

class OutgoingEventType(str, Enum):
    """Event types supported by the OutgoingEventProcessor"""
    SEND_MESSAGE = "send_message"
    EDIT_MESSAGE = "edit_message"
    DELETE_MESSAGE = "delete_message"
    ADD_REACTION = "add_reaction"
    REMOVE_REACTION = "remove_reaction"
    FETCH_HISTORY = "fetch_history"
    FETCH_ATTACHMENT = "fetch_attachment"
    PIN_MESSAGE = "pin_message"
    UNPIN_MESSAGE = "unpin_message"

class BaseOutgoingEventProcessor(ABC):
    """Processes events from socket.io and sends them to adapter client"""

    def __init__(self, config: Config, client: Any, conversation_manager: Any):
        """Initialize the socket.io events processor

        Args:
            config: Config instance
            client: A client instance
            conversation_manager: A conversation manager instance
        """
        self.config = config
        self.client = client
        self.conversation_manager = conversation_manager
        self.adapter_type = self.config.get_setting("adapter", "adapter_type")
        self.rate_limiter = RateLimiter.get_instance(self.config)
        self.outgoing_event_builder = OutgoingEventBuilder()

    async def process_event(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process an event based on its type

        Args:
            data: The event data

        Returns:
            Dict[str, Any]: Dictionary containing the status and data fields if applicable
        """
        try:
            event_handlers = {
                OutgoingEventType.SEND_MESSAGE: self._handle_send_message_event,
                OutgoingEventType.EDIT_MESSAGE: self._handle_edit_message_event,
                OutgoingEventType.DELETE_MESSAGE: self._handle_delete_message_event,
                OutgoingEventType.ADD_REACTION: self._handle_add_reaction_event,
                OutgoingEventType.REMOVE_REACTION: self._handle_remove_reaction_event,
                OutgoingEventType.FETCH_HISTORY: self._handle_fetch_history_event,
                OutgoingEventType.FETCH_ATTACHMENT: self._handle_fetch_attachment_event,
                OutgoingEventType.PIN_MESSAGE: self._handle_pin_event,
                OutgoingEventType.UNPIN_MESSAGE: self._handle_unpin_event
            }
            outgoing_event = self.outgoing_event_builder.build(data)
            handler = event_handlers.get(outgoing_event.event_type)

            return await handler(outgoing_event.data)
        except Exception as e:
            logging.error(f"Error processing event: {e}", exc_info=True)
            return {
                "request_completed": False,
                "error": f"Error processing event: {e}"
            }

    async def _handle_fetch_attachment_event(self, data: BaseModel) -> Dict[str, Any]:
        """Fetch attachment content

        Args:
            data: Event data containing attachment_id

        Returns:
            Dict[str, Any]: Dictionary containing the status and content
        """
        try:
            attachment = self.conversation_manager.attachment_cache.get_attachment_by_id(data.attachment_id)

            if attachment:
                local_file_path = os.path.join(
                    self.config.get_setting("attachments", "storage_dir"),
                    attachment.file_path
                )
                with open(local_file_path, "rb") as f:
                    return {
                        "request_completed": True,
                        "content": base64.b64encode(f.read()).decode("utf-8")
                    }
        except Exception as e:
            logging.error(f"Failed to fetch attachment {data.attachment_id}: {e}", exc_info=True)
            return {
                "request_completed": False,
                "error": f"Failed to fetch attachment: {e}"
            }

    async def _handle_send_message_event(self, data: BaseModel) -> Dict[str, Any]:
        """Send a message to a conversation

        Args:
            data: Event data containing conversation_id, text, and optional attachments

        Returns:
            Dict[str, Any]: Dictionary containing the status and message_ids
        """
        try:
            return await self._send_message(self._find_conversation(data.conversation_id), data)
        except Exception as e:
            logging.error(f"Failed to send message to conversation {data.conversation_id}: {e}", exc_info=True)
            return {
                "request_completed": False,
                "error": f"Failed to send message: {e}"
            }

    @abstractmethod
    async def _send_message(self, conversation_info: Any, data: BaseModel) -> Dict[str, Any]:
        """Send a message to a conversation"""
        raise NotImplementedError("Child classes must implement _send_message")

    async def _handle_edit_message_event(self, data: BaseModel) -> Dict[str, Any]:
        """Edit a message

        Args:
            data: Event data containing conversation_id, message_id, and text

        Returns:
            Dict[str, Any]: Dictionary containing the status
        """
        try:
            return await self._edit_message(self._find_conversation(data.conversation_id), data)
        except Exception as e:
            logging.error(f"Failed to edit message {data.message_id}: {e}", exc_info=True)
            return {
                "request_completed": False,
                "error": f"Failed to edit message: {e}"
            }

    @abstractmethod
    async def _edit_message(self, conversation_info: Any, data: BaseModel) -> Dict[str, Any]:
        """Send a message to a conversation"""
        raise NotImplementedError("Child classes must implement _edit_message")

    async def _handle_delete_message_event(self, data: BaseModel) -> Dict[str, Any]:
        """Delete a message

        Args:
            data: Event data containing conversation_id and message_id

        Returns:
            Dict[str, Any]: Dictionary containing the status
        """
        try:
            return await self._delete_message(self._find_conversation(data.conversation_id), data)
        except Exception as e:
            logging.error(f"Failed to delete message {data.message_id}: {e}", exc_info=True)
            return {
                "request_completed": False,
                "error": f"Failed to delete message: {e}"
            }

    @abstractmethod
    async def _delete_message(self, conversation_info: Any, data: BaseModel) -> Dict[str, Any]:
        """Delete a message"""
        raise NotImplementedError("Child classes must implement _delete_message")

    async def _handle_add_reaction_event(self, data: BaseModel) -> Dict[str, Any]:
        """Add a reaction to a message

        Args:
            data: Event data containing conversation_id, message_id, and emoji

        Returns:
            Dict[str, Any]: Dictionary containing the status
        """
        try:
            return await self._add_reaction(self._find_conversation(data.conversation_id), data)
        except Exception as e:
            logging.error(f"Failed to add reaction to message {data.message_id}: {e}", exc_info=True)
            return {
                "request_completed": False,
                "error": f"Failed to add reaction: {e}"
            }

    @abstractmethod
    async def _add_reaction(self, conversation_info: Any, data: BaseModel) -> Dict[str, Any]:
        """Add a reaction to a message"""
        raise NotImplementedError("Child classes must implement _add_reaction")

    async def _handle_remove_reaction_event(self, data: BaseModel) -> Dict[str, Any]:
        """Remove a specific reaction from a message

        Args:
            data: Event data containing conversation_id, message_id, and emoji

        Returns:
            Dict[str, Any]: Dictionary containing the status
        """
        try:
            return await self._remove_reaction(self._find_conversation(data.conversation_id), data)
        except Exception as e:
            logging.error(f"Failed to remove reaction from message {data.message_id}: {e}", exc_info=True)
            return {
                "request_completed": False,
                "error": f"Failed to remove reaction: {e}"
            }

    @abstractmethod
    async def _remove_reaction(self, conversation_info: Any, data: BaseModel) -> Dict[str, Any]:
        """Remove a reaction from a message"""
        raise NotImplementedError("Child classes must implement _remove_reaction")

    async def _handle_fetch_history_event(self, data: BaseModel) -> Dict[str, Any]:
        """Fetch history of a conversation

        Args:
            data: Event data containing
                  conversation_id,
                  before or after datetime as int (one of the two must be provided),
                  limit (optional, default is taken from config)

        Returns:
            Dict[str, Any]: Dictionary containing the status and history
        """
        if not data.before and not data.after:
            logging.error("No before or after datetime provided")
            return {
                "request_completed": False,
                "error": "Failed to fetch history: no before or after datetime provided"
            }

        return {"request_completed": True}

    async def _handle_pin_event(self, data: BaseModel) -> Dict[str, Any]:
        """Pin a message

        Args:
            data: Event data containing
                  conversation_id,
                  message_id

        Returns:
            Dict[str, Any]: Dictionary containing the status
        """
        try:
            return await self._pin_message(self._find_conversation(data.conversation_id), data)
        except Exception as e:
            logging.error(f"Failed to pin message {data.message_id}: {e}", exc_info=True)
            return {
                "request_completed": False,
                "error": f"Failed to pin message: {e}"
            }

    @abstractmethod
    async def _pin_message(self, conversation_info: Any, data: BaseModel) -> Dict[str, Any]:
        """Pin a message"""
        raise NotImplementedError("Child classes must implement _pin_message")

    async def _handle_unpin_event(self, data: BaseModel) -> Dict[str, Any]:
        """Unpin a message

        Args:
            data: Event data containing
                  conversation_id,
                  message_id

        Returns:
            Dict[str, Any]: Dictionary containing the status
        """
        try:
            return await self._unpin_message(self._find_conversation(data.conversation_id), data)
        except Exception as e:
            logging.error(f"Failed to unpin message {data.message_id}: {e}", exc_info=True)
            return {
                "request_completed": False,
                "error": f"Failed to unpin message: {e}"
            }

    @abstractmethod
    async def _unpin_message(self, conversation_info: Any, data: BaseModel) -> Dict[str, Any]:
        """Unpin a message"""
        raise NotImplementedError("Child classes must implement _unpin_message")

    def _find_conversation(self, conversation_id: str) -> Any:
        """Find a conversation by id

        Args:
            conversation_id: The standard conversation ID

        Returns:
            Any: The conversation info
        """
        conversation_info = self.conversation_manager.get_conversation(conversation_id)

        if not conversation_info:
            raise Exception(f"Conversation {conversation_id} not found")

        return conversation_info

    def _split_long_message(self, text: str) -> List[str]:
        """Split a long message at sentence boundaries to fit within adapter's message length limits.

        Args:
            text: The message text to split

        Returns:
            List of message parts, each under the maximum length
        """
        max_length = self.config.get_setting("adapter", "max_message_length")

        if len(text) <= max_length:
            return [text]

        sentence_endings = [".", "!", "?", ".\n", "!\n", "?\n", ".\t", "!\t", "?\t"]
        message_parts = []
        remaining_text = text

        while len(remaining_text) > max_length:
            cut_point = max_length

            for i in range(max_length - 1, max(0, max_length - 200), -1):
                for ending in sentence_endings:
                    end_pos = i - len(ending) + 1
                    if end_pos >= 0 and remaining_text[end_pos:i+1] == ending:
                        cut_point = i + 1  # Include the ending punctuation and space
                        break
                if cut_point < max_length:
                    break
            if cut_point == max_length:
                last_newline = remaining_text.rfind("\n", 0, max_length)
                if last_newline > max_length // 2:
                    cut_point = last_newline + 1
                else:
                    last_space = remaining_text.rfind(" ", max_length // 2, max_length)
                    if last_space > 0:
                        cut_point = last_space + 1
                    else:
                        cut_point = max_length

            message_parts.append(remaining_text[:cut_point])
            remaining_text = remaining_text[cut_point:]

        if remaining_text:
            message_parts.append(remaining_text)

        return message_parts
