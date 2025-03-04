import asyncio
import json
import logging
import os

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Callable, Dict, List, Union

from core.rate_limiter.rate_limiter import RateLimiter
from core.utils.config import Config

class BaseIncomingEventProcessor(ABC):
    """Incoming events processor"""

    def __init__(self, config: Config, client: Any):
        """Initialize the incoming events processor

        Args:
            config: Config instance
            client: Client instance
        """
        self.config = config
        self.client = client
        self.adapter_name = self.config.get_setting("adapter", "adapter_name")
        self.adapter_type = self.config.get_setting("adapter", "adapter_type")
        self.rate_limiter = RateLimiter.get_instance(self.config)

    async def process_event(self, event: Any) -> List[Dict[str, Any]]:
        """Process events from a client

        Args:
            event: Event object

        Returns:
            List of standardized event dictionaries to emit
        """
        try:
            event_handlers = self._get_event_handlers()
            handler = event_handlers.get(event["type"])

            if handler:
                return await handler(event)

            logging.debug(f"Unhandled event type: {event['type']}")
            return []
        except Exception as e:
            logging.error(f"Error processing event: {e}", exc_info=True)
            return []

    @abstractmethod
    def _get_event_handlers(self) -> Dict[str, Callable]:
        """Get event handlers for incoming events"""
        raise NotImplementedError("Child classes must implement _get_event_handlers")

    async def _conversation_started_event_info(self,
                                               delta: Dict[str, Any],
                                               history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create a conversation started event

        Args:
            delta: Event change information

        Returns:
            Formatted event dictionary
        """
        return {
            "adapter_type": self.adapter_type,
            "event_type": "conversation_started",
            "data" : {
                "conversation_id": delta["conversation_id"],
                "history": history
            }
        }

    async def _new_message_event_info(self, delta: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new message event

        Args:
            delta: Message data (either from a new message or a migrated message)

        Returns:
            Formatted event dictionary
        """
        return {
            "adapter_type": self.adapter_type,
            "event_type": "message_received",
            "data" : {
                "adapter_name": self.adapter_name,
                "message_id": delta["message_id"],
                "conversation_id": delta["conversation_id"],
                "sender": {
                    "user_id": delta["sender"]["user_id"] if "sender" in delta else "Unknown",
                    "display_name": delta["sender"]["display_name"] if "sender" in delta else "Unknown User"
                },
                "text": delta["text"] if "text" in delta else "",
                "thread_id": delta["thread_id"] if "thread_id" in delta else None,
                "attachments": delta["attachments"] if "attachments" in delta else [],
                "timestamp": delta["timestamp"]  # in milliseconds
            }
        }

    async def _edited_message_event_info(self, delta: Dict[str, Any]) -> Dict[str, Any]:
        """Create an edited message event

        Args:
            delta: Event change information

        Returns:
            Formatted event dictionary
        """
        return {
            "adapter_type": self.adapter_type,
            "event_type": "message_updated",
            "data" : {
                "adapter_name": self.adapter_name,
                "message_id": delta["message_id"],
                "conversation_id": delta["conversation_id"],
                "new_text": delta["text"] if "text" in delta else "",
                "timestamp": delta["timestamp"],
                "attachments": delta["attachments"] if "attachments" in delta else []
            }
        }

    async def _deleted_message_event_info(self,
                                          message_id: Union[int, str],
                                          conversation_id: Union[int, str]) -> Dict[str, Any]:
        """Create a message deleted event

        Args:
            message_id: ID of the deleted message
            conversation_id: ID of the conversation

        Returns:
            Formatted event dictionary
        """
        return {
            "adapter_type": self.adapter_type,
            "event_type": "message_deleted",
            "data" : {
                "message_id": str(message_id),
                "conversation_id": str(conversation_id)
            }
        }

    async def _reaction_update_event_info(self,
                                          event_type: str,
                                          delta: Dict[str, Any],
                                          reaction: str) -> Dict[str, Any]:
        """Create a reaction event

        Args:
            event_type: Type of reaction event (added/removed)
            delta: Event change information
            reaction: Emoji reaction

        Returns:
            Formatted event dictionary
        """
        return {
            "adapter_type": self.adapter_type,
            "event_type": event_type,
            "data" : {
                "message_id": delta["message_id"],
                "conversation_id": delta["conversation_id"],
                "emoji": reaction
            }
        }

    async def _pinned_status_change_event_info(self,
                                               event_type: str,
                                               delta: Dict[str, Any]) -> Dict[str, Any]:
        """Create a pinned message status change event

        Args:
            event_type: Type of change (pinned/unpinned)
            delta: Event change information

        Returns:
            Formatted event dictionary
        """
        return {
            "adapter_type": self.adapter_type,
            "event_type": event_type,
            "data" : {
                "message_id": delta["message_id"],
                "conversation_id": delta["conversation_id"]
            }
        }
