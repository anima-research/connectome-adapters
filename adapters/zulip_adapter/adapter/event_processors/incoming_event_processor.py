import asyncio
import logging

from enum import Enum
from typing import Any, Callable, Dict, List

from adapters.zulip_adapter.adapter.attachment_loaders.downloader import Downloader
from adapters.zulip_adapter.adapter.conversation.manager import Manager
from adapters.zulip_adapter.adapter.event_processors.history_fetcher import HistoryFetcher

from core.utils.config import Config
from core.event_processors.base_incoming_event_processor import BaseIncomingEventProcessor

class ZulipIncomingEventType(str, Enum):
    """Event types supported by the ZulipIncomingEventProcessor"""
    MESSAGE = "message"
    UPDATE_MESSAGE = "update_message"
    DELETE_MESSAGE = "delete_message"
    REACTION = "reaction"

class IncomingEventProcessor(BaseIncomingEventProcessor):
    """Zulip events processor"""

    def __init__(self, config: Config, client: Any, conversation_manager: Manager):
        """Initialize the Zulip incoming event processor

        Args:
            config: Config instance
            client: Zulip client instance
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
            ZulipIncomingEventType.MESSAGE: self._handle_message,
            ZulipIncomingEventType.UPDATE_MESSAGE: self._handle_update_message,
            ZulipIncomingEventType.DELETE_MESSAGE: self._handle_delete_message,
            ZulipIncomingEventType.REACTION: self._handle_reaction
        }

    async def _handle_message(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Handle a new message event from Zulip

        Args:
            event: Zulip event object

        Returns:
            List of events to emit
        """
        events = []

        try:
            delta = await self.conversation_manager.add_to_conversation({
                "message": event.get("message", {}),
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
                anchor=delta.get("message_id", "newest")
            ).fetch()
        except Exception as e:
            logging.error(f"Error fetching conversation history: {e}", exc_info=True)
            return []

    async def _handle_update_message(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Handle an update message event from Zulip

        Args:
            event: Zulip event object

        Returns:
            List of events to emit
        """
        try:
            if self._is_topic_change(event):
                return await self._handle_topic_change(event)
            else:
                return await self._handle_message_change(event)
        except Exception as e:
            logging.error(f"Error handling edited message: {e}", exc_info=True)

        return []

    def _is_topic_change(self, event: Dict[str, Any]) -> bool:
        """Check if the event is a topic change

        Args:
            event: Zulip event object

        Returns:
            True if the event is a topic change, False otherwise
        """
        subject = event.get("subject", None)
        orig_subject = event.get("orig_subject", None)

        return subject and orig_subject and subject != orig_subject

    async def _handle_topic_change(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Handle a topic change event

        Args:
            event: Zulip event object

        Returns:
            List of events to emit
        """
        events = []
        delta = await self.conversation_manager.migrate_between_conversations(event)

        if delta:
            if delta.get("fetch_history", False):
                history = await self._fetch_conversation_history(delta)
                events.append(self.incoming_event_builder.conversation_started(delta, history))

            old_conversation_id = f"{event.get('stream_id', '')}/{event.get('orig_subject', '')}"
            for message_id in delta.get("deleted_message_ids", []):
                events.append(
                    self.incoming_event_builder.message_deleted(message_id, old_conversation_id)
                )
            for migrated_message in delta.get("added_messages", []):
                events.append(self.incoming_event_builder.message_received(migrated_message))

        return events

    async def _handle_message_change(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Handle a message change event

        Args:
            event: Zulip event object

        Returns:
            List of events to emit
        """
        events = []
        delta = await self.conversation_manager.update_conversation({
            "event_type": "update_message",
            "message": event,
            "attachments": await self.downloader.download_attachment(event)
        })

        if delta:
            for message in delta.get("updated_messages", []):
                events.append(self.incoming_event_builder.message_updated(message))

        return events

    async def _handle_delete_message(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Handle a delete message event

        Args:
            event: Zulip event object

        Returns:
            List of events to emit
        """
        events = []

        try:
            delta = await self.conversation_manager.delete_from_conversation(
                incoming_event=event
            )

            if delta:
                for deleted_id in delta.get("deleted_message_ids", []):
                    events.append(
                        self.incoming_event_builder.message_deleted(deleted_id, delta["conversation_id"])
                    )
        except Exception as e:
            logging.error(f"Error handling delete event: {e}", exc_info=True)

        return events

    async def _handle_reaction(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Handle chat action events like user joins, leaves, or group migrations

        Args:
            event: Zulip event object

        Returns:
            List of events to emit (typically empty for this case)
        """
        events = []

        try:
            delta = await self.conversation_manager.update_conversation({
                "event_type": "reaction",
                "message": event
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
