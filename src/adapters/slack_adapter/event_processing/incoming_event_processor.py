import asyncio
import logging

from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from src.adapters.slack_adapter.conversation.manager import Manager
from src.adapters.slack_adapter.event_processing.attachment_loaders.downloader import Downloader
from src.adapters.slack_adapter.event_processing.history_fetcher import HistoryFetcher
from src.adapters.slack_adapter.event_processing.user_info_preprocessor import UserInfoPreprocessor

from src.core.utils.config import Config
from src.core.events.processors.base_incoming_event_processor import BaseIncomingEventProcessor

class SlackIncomingEventType(str, Enum):
    """Event types supported by the SlackIncomingEventProcessor"""
    NEW_MESSAGE = "message"
    EDITED_MESSAGE = "message_changed"
    DELETED_MESSAGE = "message_deleted"
    ADDED_REACTION = "reaction_added"
    REMOVED_REACTION = "reaction_removed"
    ADDED_PIN = "pin_added"
    REMOVED_PIN = "pin_removed"
    FETCH_HISTORY = "fetch_history"
    TEAM_RENAME = "team_rename"
    CHANNEL_RENAME = "channel_rename"

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
        super().__init__(config, client, conversation_manager)
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
            SlackIncomingEventType.REMOVED_PIN: self._handle_pin,
            SlackIncomingEventType.FETCH_HISTORY: self._handle_fetch_history,
            SlackIncomingEventType.TEAM_RENAME: self._handle_rename,
            SlackIncomingEventType.CHANNEL_RENAME: self._handle_rename
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
            team = None
            channel = None

            if not await self.conversation_manager.conversation_exists(event):
                team = await self._get_team_info(event)
                channel = await self._get_channel_info(event)

            attachments = await self.downloader.download_attachments(event)
            initial_event_details = {"message": event, "attachments": attachments, "server": team, "platform_conversation": channel}
            user_info_preprocessor = UserInfoPreprocessor(self.config, self.client)
            initial_event_details.update(await user_info_preprocessor.process_incoming_event(event))

            delta = await self.conversation_manager.add_to_conversation(initial_event_details)

            if delta:
                added_messages = delta.get("added_messages", [])
                anchor = (added_messages[-1].get("message_id", None) if added_messages else None)

                await self._add_new_conversation_events(events, delta, anchor=anchor)

                for message in added_messages:
                    events.append(self.incoming_event_builder.message_received(message))
        except Exception as e:
            logging.error(f"Error handling new message: {e}", exc_info=True)

        return events

    async def _handle_edited_message(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Handle an edited message event from Slack

        Args:
            event: Slack event object

        Returns:
            List of events to emit
        """
        try:
            events = []

            initial_event_details = {"event_type": "edited_message", "message": event["event"]}
            user_info_preprocessor = UserInfoPreprocessor(self.config, self.client)
            initial_event_details.update(await user_info_preprocessor.process_incoming_event(event["event"]))

            delta = await self.conversation_manager.update_conversation(initial_event_details)

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

    async def _get_team_info(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Get team info for a given event

        Args:
            event: Slack event object

        Returns:
            User info dictionary
        """
        try:
            team_info = await self.client.team_info(team=event.get("team", ""))
            if team_info:
                return team_info.get("team", {})
        except Exception as e:
            logging.error(f"Error fetching team info: {e}")

        return {}

    async def _get_channel_info(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Get channel info for a given event

        Args:
            event: Slack event object

        Returns:
            User info dictionary
        """
        try:
            channel_info = await self.client.conversations_info(channel=event.get("channel", ""))
            if channel_info:
                return channel_info.get("channel", {})
        except Exception as e:
            logging.error(f"Error fetching channel info: {e}")

        return {}

    def _history_fetcher_class(self):
        """History fetcher class"""
        return HistoryFetcher
