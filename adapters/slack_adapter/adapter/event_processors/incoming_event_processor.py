import asyncio
import logging

from enum import Enum
from typing import Any, Callable, Dict, List

from adapters.slack_adapter.adapter.attachment_loaders.downloader import Downloader
from adapters.slack_adapter.adapter.conversation.manager import Manager
from adapters.slack_adapter.adapter.event_processors.history_fetcher import HistoryFetcher

from core.utils.config import Config
from core.event_processors.base_incoming_event_processor import BaseIncomingEventProcessor

class SlackIncomingEventType(str, Enum):
    """Event types supported by the SlackIncomingEventProcessor"""
    NEW_MESSAGE = "message"
    EDITED_MESSAGE = "message_changed"
    DELETED_MESSAGE = "message_deleted"
    ADDED_REACTION = "reaction_added"
    REMOVED_REACTION = "reaction_removed"
    ADDED_PIN = "pin_added"
    REMOVED_PIN = "pin_removed"

class IncomingEventProcessor(BaseIncomingEventProcessor):
    """Slack events processor"""

    def __init__(self,
                 config: Config,
                 client: Any,
                 conversation_manager: Manager):
        """Initialize the Slack incoming event processor

        Args:
            config: Config instance
            client: Slack client instance
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
            SlackIncomingEventType.NEW_MESSAGE: self._handle_message,
            SlackIncomingEventType.EDITED_MESSAGE: self._handle_edited_message,
            SlackIncomingEventType.DELETED_MESSAGE: self._handle_deleted_message,
            SlackIncomingEventType.ADDED_REACTION: self._handle_reaction,
            SlackIncomingEventType.REMOVED_REACTION: self._handle_reaction,
            SlackIncomingEventType.ADDED_PIN: self._handle_pin,
            SlackIncomingEventType.REMOVED_PIN: self._handle_pin
        }

    async def _handle_message(self, event: Any) -> List[Dict[str, Any]]:
        """Handle a new message event from Slack

        Args:
            event: Dict with event type, team_id, and event

        Returns:
            List of events to emit
        """
        event = event.get("event", {})
        events = []

        try:
            delta = await self.conversation_manager.add_to_conversation({
                "message": event,
                "user": await self._get_user_info(event),
                "attachments": await self.downloader.download_attachments(event)
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
            messages = delta.get("added_messages", [])
            if messages:
                return await HistoryFetcher(
                    self.config,
                    self.client,
                    self.conversation_manager,
                    delta["conversation_id"],
                    anchor=messages[-1].get("message_id", None)
                ).fetch()
        except Exception as e:
            logging.error(f"Error fetching conversation history: {e}", exc_info=True)

        return []

    async def _handle_edited_message(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Handle an edited message event from Slack

        Args:
            event: Slack event object

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

            return events
        except Exception as e:
            logging.error(f"Error handling edited message: {e}", exc_info=True)

        return []

    async def _handle_deleted_message(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Handle a deleted message event from Slack

        Args:
            event: Slack event object

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
        """Handle reaction events

        Args:
            event: Slack event object

        Returns:
            List of events to emit (typically empty for this case)
        """
        events = []

        try:
            delta = await self.conversation_manager.update_conversation({
                "event_type": "reaction",
                "message": event["event"]
            })

            if delta:
                for reaction in delta.get("added_reactions", []):
                    events.append(
                        self.incoming_event_builder.reaction_update(
                            "reaction_added", delta, reaction
                        )
                    )
                for reaction in delta.get("removed_reactions", []):
                    events.append(
                        self.incoming_event_builder.reaction_update(
                            "reaction_removed", delta, reaction
                        )
                    )
        except Exception as e:
            logging.error(f"Error handling reaction event: {e}", exc_info=True)

        return events

    async def _handle_pin(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Handle pin events

        Args:
            event: Slack event object

        Returns:
            List of events to emit (typically empty for this case)
        """
        events = []

        try:
            delta = await self.conversation_manager.update_conversation({
                "event_type": "pin",
                "message": event["event"]
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
            logging.error(f"Error handling reaction event: {e}", exc_info=True)

        return events

    async def _get_user_info(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Get user info for a given event

        Args:
            event: Slack event object

        Returns:
            User info dictionary
        """
        try:
            user_id = event.get("user", "")
            user_info = await self.client.users_info(user=user_id)

            if user_info:
                return user_info.get("user", {})
        except Exception as e:
            logging.error(f"Error fetching user info: {e}")

        return {}
