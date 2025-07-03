import asyncio
import logging

from enum import Enum
from typing import Any, Callable, Dict, List

from src.adapters.zulip_adapter.attachment_loaders.downloader import Downloader
from src.adapters.zulip_adapter.conversation.manager import Manager
from src.adapters.zulip_adapter.event_processors.history_fetcher import HistoryFetcher

from src.core.utils.config import Config
from src.core.events.processors.base_incoming_event_processor import BaseIncomingEventProcessor

class ZulipIncomingEventType(str, Enum):
    """Event types supported by the ZulipIncomingEventProcessor"""
    MESSAGE = "message"
    UPDATE_MESSAGE = "update_message"
    DELETE_MESSAGE = "delete_message"
    REACTION = "reaction"
    REALM = "realm"
    STREAM = "stream"
    FETCH_HISTORY = "fetch_history"

class IncomingEventProcessor(BaseIncomingEventProcessor):
    """Zulip events processor"""

    def __init__(self, config: Config, client: Any, conversation_manager: Manager):
        """Initialize the Zulip incoming event processor

        Args:
            config: Config instance
            client: Zulip client instance
            conversation_manager: Conversation manager for tracking message history
        """
        super().__init__(config, client, conversation_manager)
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
            ZulipIncomingEventType.REACTION: self._handle_reaction,
            ZulipIncomingEventType.REALM: self._handle_rename,
            ZulipIncomingEventType.STREAM: self._handle_rename,
            ZulipIncomingEventType.FETCH_HISTORY: self._handle_fetch_history
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
            message = event.get("message", {})

            if self._skip_message(message):
                return events

            server = None
            if not await self.conversation_manager.conversation_exists(message):
                server = self.client.get_server_settings()

            delta = await self.conversation_manager.add_to_conversation({
                "message": message,
                "attachments": await self.downloader.download_attachment(message),
                "server": server
            })

            if delta:
                await self._add_new_conversation_events(events, delta)

                for message in delta.get("added_messages", []):
                    events.append(self.incoming_event_builder.message_received(message))
        except Exception as e:
            logging.error(f"Error handling new message: {e}", exc_info=True)

        return events

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
        delta = await self.conversation_manager.migrate_between_conversations(
            {"message": event, "server": self.client.get_server_settings()}
        )

        if delta:
            await self._add_new_conversation_events(events=events, delta=delta, exclude_messages=False)

            old_conversation_id = f"{event.get('stream_id', '')}/{event.get('orig_subject', '')}"
            old_conversation = self.conversation_manager.get_conversation(old_conversation_id)

            if old_conversation:
                for message_id in delta.get("deleted_message_ids", []):
                    events.append(
                        self.incoming_event_builder.message_deleted(
                            message_id, old_conversation.conversation_id
                        )
                    )

            for message in delta.get("added_messages", []):
                events.append(self.incoming_event_builder.message_received(message))

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

    async def _handle_rename(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Handle a team or channel rename event from Zulip

        Args:
            event: An event object

        Returns:
            List of events to emit
        """
        return await super()._handle_rename({"event": event})

    def _history_fetcher_class(self):
        """History fetcher class"""
        return HistoryFetcher

    def _skip_message(self, message: Dict[str, Any]) -> bool:
        """Check if the message should be skipped.
        We skip service messages and messages not directed to the bot that violates privacy
        (the last case happens when we mention the bot in DM-s in which our bot does not participate).

        Args:
            message: Zulip message object

        Returns:
            True if the message should be skipped, False otherwise
        """
        if message.get("sender_realm_str", "") == "zulipinternal":
            return True

        recipients = message.get("display_recipient", [])
        adapter_id = self.config.get_setting("adapter", "adapter_id")

        if not isinstance(recipients, list):
            return False

        for recipient in recipients:
            if str(recipient.get("id", "")) == adapter_id:
                return False

        return True
