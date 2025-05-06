import asyncio
import json
import logging
import os
import telethon

from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from adapters.telegram_adapter.adapter.attachment_loaders.downloader import Downloader
from adapters.telegram_adapter.adapter.conversation.manager import Manager
from adapters.telegram_adapter.adapter.event_processors.history_fetcher import HistoryFetcher

from core.event_processors.base_incoming_event_processor import BaseIncomingEventProcessor
from core.utils.config import Config

class TelegramIncomingEventType(str, Enum):
    """Event types supported by the TelegramIncomingEventProcessor"""
    NEW_MESSAGE = "new_message"
    EDITED_MESSAGE = "edited_message"
    DELETED_MESSAGE = "deleted_message"
    CHAT_ACTION = "chat_action"

class IncomingEventProcessor(BaseIncomingEventProcessor):
    """Telegram events processor"""

    def __init__(self, config: Config, client: Any, conversation_manager: Manager):
        """Initialize the Telegram events processor

        Args:
            config: Config instance
            client: Telethon client instance
            conversation_manager: Conversation manager for tracking message history
        """
        super().__init__(config, client)
        self.conversation_manager = conversation_manager
        self.downloader = Downloader(self.config, self.client)

    def _get_event_handlers(self) -> Dict[str, Callable]:
        """Get event handlers for incoming events

        Returns:
            Dictionary of event handlers
        """
        return {
            TelegramIncomingEventType.NEW_MESSAGE: self._handle_new_message,
            TelegramIncomingEventType.EDITED_MESSAGE: self._handle_edited_message,
            TelegramIncomingEventType.DELETED_MESSAGE: self._handle_deleted_message,
            TelegramIncomingEventType.CHAT_ACTION: self._handle_chat_action
        }

    async def _handle_new_message(self, event: Any) -> List[Dict[str, Any]]:
        """Handle a new message event from Telegram

        Args:
            event: Dictionary containing the event data

        Returns:
            List of events to emit
        """
        events = []

        try:
            message = event["event"].message
            delta = await self.conversation_manager.add_to_conversation({
                "message": message,
                "user": await self._get_user(message),
                "attachments": [
                    await self.downloader.download_attachment(
                        message,
                        self.conversation_manager.attachment_download_required(message)
                    )
                ]
            })

            if delta:
                if delta.get("fetch_history", False):
                    history = await self._fetch_conversation_history(delta["conversation_id"])
                    events.append(self.incoming_event_builder.conversation_started(delta, history))

                for message in delta.get("added_messages", []):
                    events.append(self.incoming_event_builder.message_received(message))
        except Exception as e:
            logging.error(f"Error handling new message: {e}", exc_info=True)

        return events

    async def _handle_edited_message(self, event: Any) -> List[Dict[str, Any]]:
        """Handle an edited message event from Telethon

        Args:
            event: Dictionary containing the event data

        Returns:
            List of events to emit
        """
        events = []

        try:
            delta = await self.conversation_manager.update_conversation({
                "event_type": "edited_message",
                "message": event["event"].message
            })

            if delta:
                for message in delta.get("updated_messages", []):
                    events.append(self.incoming_event_builder.message_updated(message))
                for reaction in delta.get("added_reactions", []):
                    events.append(
                        self.incoming_event_builder.reaction_update("reaction_added", delta, reaction)
                    )
                for reaction in delta.get("removed_reactions", []):
                    events.append(
                        self.incoming_event_builder.reaction_update("reaction_removed", delta, reaction)
                    )
        except Exception as e:
            logging.error(f"Error handling edited message: {e}", exc_info=True)

        return events

    async def _handle_deleted_message(self, event: Any) -> List[Dict[str, Any]]:
        """Handle a deleted message event from Telethon

        Args:
            event: Dictionary containing the event data

        Returns:
            List of events to emit
        """
        events = []

        try:
            delta = await self.conversation_manager.delete_from_conversation(
                incoming_event={"event": event["event"]}
            )

            if delta:
                for deleted_id in delta.get("deleted_message_ids", []):
                    events.append(
                        self.incoming_event_builder.message_deleted(deleted_id, delta["conversation_id"])
                    )
        except Exception as e:
            logging.error(f"Error handling deleted message: {e}", exc_info=True)

        return events

    async def _handle_chat_action(self, event: Any) -> List[Dict[str, Any]]:
        """Handle chat action events like user joins, leaves, or group migrations

        Args:
            event: Dictionary containing the event data

        Returns:
            List of events to emit (typically empty for this case)
        """
        events = []

        try:
            message = event["event"].action_message

            if message and hasattr(message, "action"):
                action = message.action
                action_type = type(action).__name__

                if action_type == "MessageActionPinMessage":
                    delta = await self.conversation_manager.update_conversation({
                        "event_type": "pinned_message",
                        "message": message
                    })

                    if delta:
                        for message_id in delta.get("pinned_message_ids", []):
                            events.append(
                                self.incoming_event_builder.pin_status_update(
                                    "message_pinned",
                                    {
                                        "message_id": message_id,
                                        "conversation_id": delta["conversation_id"]
                                    }
                                )
                            )
            elif not message and hasattr(event["event"], "original_update"):
                delta = await self.conversation_manager.update_conversation({
                    "event_type": "unpinned_message",
                    "message": event["event"].original_update
                })

                if delta:
                    for message_id in delta.get("unpinned_message_ids", []):
                        events.append(
                            self.incoming_event_builder.pin_status_update(
                                "message_unpinned",
                                {
                                    "message_id": message_id,
                                    "conversation_id": delta["conversation_id"]
                                }
                            )
                        )
        except Exception as e:
            logging.error(f"Error handling chat action: {e}", exc_info=True)

        return events

    async def _fetch_conversation_history(self,
                                          conversation_id: str) -> List[Dict[str, Any]]:
        """Fetch and format recent conversation history from Telegram

        Args:
            conversation_id: ID of the conversation
            message_id: ID of the message that triggered the history fetch

        Returns:
            List of formatted message objects for the history
        """
        try:
            return await HistoryFetcher(
                self.config,
                self.client,
                self.conversation_manager,
                conversation_id,
                anchor="newest"
            ).fetch()
        except Exception as e:
            logging.error(f"Error fetching conversation history: {e}", exc_info=True)
            return []

    async def _get_user(self, message: Any) -> Optional[Any]:
        """Get user information from Telegram

        Args:
            message: Telethon message object

        Returns:
            Telethon user object or None if not found
        """
        try:
            await self.rate_limiter.limit_request("get_user")

            if message and hasattr(message, "from_id") and hasattr(message.from_id, "user_id"):
                return await self.client.get_entity(int(message.from_id.user_id))
            if message and hasattr(message, "peer_id") and hasattr(message.peer_id, "user_id"):
                return await self.client.get_entity(int(message.peer_id.user_id))
        except Exception as e:
            logging.error(f"Error getting user: {e}")

        return None
