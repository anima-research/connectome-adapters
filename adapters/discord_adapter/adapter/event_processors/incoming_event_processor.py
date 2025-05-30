import asyncio
import discord
import logging

from enum import Enum
from typing import Any, Callable, Dict, List, Union

from adapters.discord_adapter.adapter.attachment_loaders.downloader import Downloader
from adapters.discord_adapter.adapter.conversation.manager import Manager
from adapters.discord_adapter.adapter.event_processors.discord_utils import is_discord_service_message
from adapters.discord_adapter.adapter.event_processors.history_fetcher import HistoryFetcher

from core.utils.config import Config
from core.events.processors.base_incoming_event_processor import BaseIncomingEventProcessor

class DiscordIncomingEventType(str, Enum):
    """Event types supported by the DiscordIncomingEventProcessor"""
    NEW_MESSAGE = "new_message"
    EDITED_MESSAGE = "edited_message"
    DELETED_MESSAGE = "deleted_message"
    ADDED_REACTION = "added_reaction"
    REMOVED_REACTION = "removed_reaction"

class IncomingEventProcessor(BaseIncomingEventProcessor):
    """Discord events processor"""

    def __init__(self, config: Config, client: Any, conversation_manager: Manager):
        """Initialize the Discord incoming event processor

        Args:
            config: Config instance
            client: Discord client instance
            conversation_manager: Conversation manager for tracking message history
        """
        super().__init__(config, client)
        self.conversation_manager = conversation_manager
        self.downloader = Downloader(self.config)

    def _get_event_handlers(self) -> Dict[str, Callable]:
        """Get event handlers for incoming events

        Returns:
            Dictionary of event handlers
        """
        return {
            DiscordIncomingEventType.NEW_MESSAGE: self._handle_message,
            DiscordIncomingEventType.EDITED_MESSAGE: self._handle_edited_message,
            DiscordIncomingEventType.DELETED_MESSAGE: self._handle_deleted_message,
            DiscordIncomingEventType.ADDED_REACTION: self._handle_reaction,
            DiscordIncomingEventType.REMOVED_REACTION: self._handle_reaction
        }

    async def _handle_message(self, event: Any) -> List[Dict[str, Any]]:
        """Handle a new message event from Discord

        Args:
            event: Discord event object

        Returns:
            List of events to emit
        """
        event = event.get("event", None)
        events = []

        try:
            if is_discord_service_message(event):
                return events

            delta = await self.conversation_manager.add_to_conversation({
                "message": event,
                "attachments": await self.downloader.download_attachment(event)
            })

            if delta:
                if delta.get("fetch_history", False):
                    history = await self._fetch_conversation_history(delta)
                    events.append(self.incoming_event_builder.conversation_started(delta, history))

                for message in delta.get("added_messages", []):
                    events.append(self.incoming_event_builder.message_received(message))
        except Exception as e:
            logging.error(f"Error handling new message: {e}", exc_info=True)

        return events

    async def _fetch_conversation_history(self, delta: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fetch conversation history

        Args:
            delta: Event change information containing conversation ID

        Returns:
            List of formatted message history
        """
        try:
            return await HistoryFetcher(
                self.config,
                self.client,
                self.conversation_manager,
                delta["conversation_id"],
                anchor="newest"
            ).fetch()
        except Exception as e:
            logging.error(f"Error fetching conversation history: {e}", exc_info=True)
            return []

    async def _handle_edited_message(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Handle an edited message event from Discord

        Args:
            event: Discord event object

        Returns:
            List of events to emit
        """
        try:
            events = []
            delta = await self.conversation_manager.update_conversation({
                "event_type": "edited_message",
                "message": event["event"]
            })

            if delta:
                for message in delta.get("updated_messages", []):
                    events.append(self.incoming_event_builder.message_updated(message))
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

            return events
        except Exception as e:
            logging.error(f"Error handling edited message: {e}", exc_info=True)

        return []

    async def _handle_deleted_message(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Handle a deleted message event from Discord

        Args:
            event: Discord event object

        Returns:
            List of events to emit
        """
        try:
            events = []
            delta = await self.conversation_manager.delete_from_conversation(
                incoming_event=event["event"]
            )

            if delta:
                for deleted_id in delta.get("deleted_message_ids", []):
                    events.append(
                        self.incoming_event_builder.message_deleted(
                            deleted_id, delta["conversation_id"]
                        )
                    )

            return events
        except Exception as e:
            logging.error(f"Error handling deleted message: {e}", exc_info=True)

        return []

    async def _handle_reaction(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Handle chat action events like user joins, leaves, or group migrations

        Args:
            event: Discord event object

        Returns:
            List of events to emit (typically empty for this case)
        """
        events = []

        try:
            delta = await self.conversation_manager.update_conversation({
                "event_type": event["type"],
                "message": event["event"]
            })

            if delta:
                for reaction in delta.get("added_reactions", []):
                    events.append(
                        self.incoming_event_builder.reaction_update("reaction_added", delta, reaction)
                    )
                for reaction in delta.get("removed_reactions", []):
                    events.append(
                        self.incoming_event_builder.reaction_update("reaction_removed", delta, reaction)
                    )
        except Exception as e:
            logging.error(f"Error handling reaction event: {e}", exc_info=True)

        return events
