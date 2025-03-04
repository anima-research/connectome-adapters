import asyncio
import emoji
import json
import logging
import os

from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, List

from core.rate_limiter.rate_limiter import RateLimiter
from core.utils.config import Config

class OutgoingEventType(str, Enum):
    """Event types supported by the OutgoingEventProcessor"""
    SEND_MESSAGE = "send_message"
    EDIT_MESSAGE = "edit_message"
    DELETE_MESSAGE = "delete_message"
    ADD_REACTION = "add_reaction"
    REMOVE_REACTION = "remove_reaction"
    FETCH_HISTORY = "fetch_history"

class BaseOutgoingEventProcessor(ABC):
    """Processes events from socket.io and sends them to adapter client"""

    def __init__(self, config: Config, client: Any):
        """Initialize the socket.io events processor

        Args:
            config: Config instance
            client: A client instance
        """
        self.config = config
        self.client = client
        self.adapter_type = self.config.get_setting("adapter", "type")
        self.rate_limiter = RateLimiter.get_instance(self.config)

    async def process_event(self, event_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process an event based on its type

        Args:
            event_type: The type of event to process
            data: The event data

        Returns:
            Dict[str, Any]: Dictionary containing the status and data fields if applicable
        """
        event_handlers = {
            OutgoingEventType.SEND_MESSAGE: self._handle_send_message_event,
            OutgoingEventType.EDIT_MESSAGE: self._handle_edit_message_event,
            OutgoingEventType.DELETE_MESSAGE: self._handle_delete_message_event,
            OutgoingEventType.ADD_REACTION: self._handle_add_reaction_event,
            OutgoingEventType.REMOVE_REACTION: self._handle_remove_reaction_event,
            OutgoingEventType.FETCH_HISTORY: self._handle_fetch_history_event
        }

        handler = event_handlers.get(event_type)
        if handler:
            return await handler(data)

        logging.error(f"Unknown event type: {event_type}")
        return {"request_completed": False}

    async def _handle_send_message_event(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Send a message to a conversation

        Args:
            data: Event data containing conversation_id, text, and optional attachments

        Returns:
            Dict[str, Any]: Dictionary containing the status and message_ids
        """
        if not self._validate_fields(
            data, ["conversation_id", "text"], OutgoingEventType.SEND_MESSAGE
        ):
            return {"request_completed": False}

        try:
            return await self._send_message(data)
        except Exception as e:
            logging.error(
                f"Failed to send message to conversation {data['conversation_id']}: {e}",
                exc_info=True
            )
            return {"request_completed": False}

    @abstractmethod
    async def _send_message(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Send a message to a conversation"""
        raise NotImplementedError("Child classes must implement _send_message")

    async def _handle_edit_message_event(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Edit a message

        Args:
            data: Event data containing conversation_id, message_id, and text

        Returns:
            Dict[str, Any]: Dictionary containing the status
        """
        if not self._validate_fields(
            data, ["conversation_id", "message_id", "text"], OutgoingEventType.EDIT_MESSAGE
        ):
            return {"request_completed": False}

        try:
            return await self._edit_message(data)
        except Exception as e:
            logging.error(
                f"Failed to edit message {data['message_id']}: {e}",
                exc_info=True
            )
            return {"request_completed": False}

    @abstractmethod
    async def _edit_message(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Send a message to a conversation"""
        raise NotImplementedError("Child classes must implement _edit_message")

    async def _handle_delete_message_event(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Delete a message

        Args:
            data: Event data containing conversation_id and message_id

        Returns:
            Dict[str, Any]: Dictionary containing the status
        """
        if not self._validate_fields(
            data, ["conversation_id", "message_id"], OutgoingEventType.DELETE_MESSAGE
        ):
            return {"request_completed": False}

        try:
            return await self._delete_message(data)
        except Exception as e:
            logging.error(
                f"Failed to delete message {data['message_id']}: {e}",
                exc_info=True
            )
            return {"request_completed": False}

    @abstractmethod
    async def _delete_message(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Delete a message"""
        raise NotImplementedError("Child classes must implement _delete_message")

    async def _handle_add_reaction_event(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Add a reaction to a message

        Args:
            data: Event data containing conversation_id, message_id, and emoji

        Returns:
            Dict[str, Any]: Dictionary containing the status
        """
        if not self._validate_fields(
            data, ["conversation_id", "message_id", "emoji"], OutgoingEventType.ADD_REACTION
        ):
            return {"request_completed": False}

        try:
            return await self._add_reaction(data)
        except Exception as e:
            logging.error(
                f"Failed to add reaction to message {data['message_id']}: {e}",
                exc_info=True
            )
            return {"request_completed": False}

    @abstractmethod
    async def _add_reaction(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Add a reaction to a message"""
        raise NotImplementedError("Child classes must implement _add_reaction")

    async def _handle_remove_reaction_event(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Remove a specific reaction from a message

        Args:
            data: Event data containing conversation_id, message_id, and emoji

        Returns:
            Dict[str, Any]: Dictionary containing the status
        """
        if not self._validate_fields(
            data, ["conversation_id", "message_id", "emoji"], OutgoingEventType.REMOVE_REACTION
        ):
            return {"request_completed": False}

        try:
            return await self._remove_reaction(data)
        except Exception as e:
            logging.error(
                f"Failed to remove reaction from message {data['message_id']}: {e}",
                exc_info=True
            )
            return {"request_completed": False}

    @abstractmethod
    async def _remove_reaction(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Remove a reaction from a message"""
        raise NotImplementedError("Child classes must implement _remove_reaction")

    async def _handle_fetch_history_event(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch history of a conversation

        Args:
            data: Event data containing
                  conversation_id,
                  before or after datetime as int (one of the two must be provided),
                  limit (optional, default is taken from config)

        Returns:
            Dict[str, Any]: Dictionary containing the status and history
        """
        if not self._validate_fields(
            data, ["conversation_id"], OutgoingEventType.FETCH_HISTORY
        ):
            return {"request_completed": False}

        try:
            return await self._fetch_history(data)
        except Exception as e:
            logging.error(
                f"Failed to fetch history of conversation {data['conversation_id']}: {e}",
                exc_info=True
            )
            return {"request_completed": False}

    @abstractmethod
    async def _fetch_history(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch history of a conversation"""
        raise NotImplementedError("Child classes must implement _fetch_history")

    def _validate_fields(self,
                         data: Dict[str, Any],
                         required_fields: List[str],
                         operation: str) -> bool:
        """Validate that required fields are present in the data

        Args:
            data: The data to validate
            required_fields: List of required field names
            operation: Name of the operation for error logging

        Returns:
            bool: True if all required fields are present, False otherwise
        """
        missing_fields = [field for field in required_fields if not data.get(field)]

        if missing_fields:
            logging.error(f"{', '.join(missing_fields)} are required for {operation}")
            return False

        return True

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
