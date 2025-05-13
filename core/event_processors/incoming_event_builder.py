from typing import Any, Dict, List, Union
from core.event_processors.incoming_events import (
    SenderInfo,
    IncomingAttachmentInfo,
    ConversationStartedData,
    MessageReceivedData,
    MessageUpdatedData,
    MessageDeletedData,
    ReactionUpdateData,
    PinStatusUpdateData,
    ConversationStartedEvent,
    MessageReceivedEvent,
    MessageUpdatedEvent,
    MessageDeletedEvent,
    ReactionAddedEvent,
    ReactionRemovedEvent,
    MessagePinnedEvent,
    MessageUnpinnedEvent
)

class IncomingEventBuilder:
    """
    Event builder for constructing standardized events to send to the framework.
    This class handles the construction of properly formatted event dictionaries
    with Pydantic validation.
    """

    def __init__(self, adapter_type: str, adapter_name: str):
        """
        Initialize the EventBuilder with the adapter type.

        Args:
            adapter_type: The adapter type (telegram, discord, etc.)
            adapter_name: Name of the adapter instance
        """
        self.adapter_type = adapter_type
        self.adapter_name = adapter_name

    def conversation_started(self,
                             delta: Dict[str, Any],
                             history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Create a conversation_started event with validation.

        Args:
            delta: Event change information
            history: List of message history items

        Returns:
            Dictionary containing the validated event
        """
        event = ConversationStartedEvent(
            adapter_type=self.adapter_type,
            data=ConversationStartedData(
                conversation_id=delta["conversation_id"],
                history=[self._process_message(message) for message in history]
            )
        )
        return event.model_dump()

    def message_received(self, delta: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a message_received event with validation.

        Args:
            delta: Event change information

        Returns:
            Dictionary containing the validated event
        """
        event = MessageReceivedEvent(
            adapter_type=self.adapter_type,
            data=self._process_message(delta)
        )
        return event.model_dump()

    def message_updated(self, delta: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a message_updated event with validation.

        Args:
            delta: Event change information

        Returns:
            Dictionary containing the validated event
        """
        event = MessageUpdatedEvent(
            adapter_type=self.adapter_type,
            data=MessageUpdatedData(
                adapter_name=self.adapter_name,
                message_id=delta["message_id"],
                conversation_id=delta["conversation_id"],
                new_text=delta.get("text", ""),
                timestamp=delta["timestamp"],
                attachments=[IncomingAttachmentInfo(**attachment) for attachment in delta.get("attachments", [])]
            )
        )
        return event.model_dump()

    def message_deleted(self,
                        message_id: Union[int, str],
                        conversation_id: Union[int, str]) -> Dict[str, Any]:
        """
        Create a message_deleted event with validation.

        Args:
            message_id: ID of the deleted message
            conversation_id: ID of the conversation

        Returns:
            Dictionary containing the validated event
        """
        event = MessageDeletedEvent(
            adapter_type=self.adapter_type,
            data=MessageDeletedData(
                message_id=str(message_id),
                conversation_id=str(conversation_id)
            )
        )
        return event.model_dump()

    def reaction_update(self,
                        event_type: str,
                        delta: Dict[str, Any],
                        reaction: str) -> Dict[str, Any]:
        """
        Create a reaction_update event with validation.

        Args:
            event_type: Type of reaction event (added/removed)
            delta: Event change information
            reaction: Emoji reaction

        Returns:
            Dictionary containing the validated event
        """
        data = ReactionUpdateData(
            message_id=delta["message_id"],
            conversation_id=delta["conversation_id"],
            emoji=reaction
        )

        if event_type == "reaction_added":
            event = ReactionAddedEvent(
                adapter_type=self.adapter_type,
                data=data
            )
        elif event_type == "reaction_removed":
            event = ReactionRemovedEvent(
                adapter_type=self.adapter_type,
                data=data
            )
        else:
            raise ValueError(f"Unknown reaction event type: {event_type}")

        return event.model_dump()

    def pin_status_update(self, event_type: str, delta: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a pin status update event with validation.

        Args:
            event_type: Type of pin event (pinned/unpinned)
            delta: Event change information

        Returns:
            Dictionary containing the validated event
        """
        data = PinStatusUpdateData(
            message_id=delta["message_id"],
            conversation_id=delta["conversation_id"]
        )

        if event_type == "message_pinned":
            event = MessagePinnedEvent(
                adapter_type=self.adapter_type,
                data=data
            )
        elif event_type == "message_unpinned":
            event = MessageUnpinnedEvent(
                adapter_type=self.adapter_type,
                data=data
            )
        else:
            raise ValueError(f"Unknown pin status event type: {event_type}")

        return event.model_dump()

    def _process_message(self, delta: Dict[str, Any]) -> MessageReceivedData:
        """
        Process a message delta and return a MessageReceivedData object.

        Args:
            delta: Event change information

        Returns:
            MessageReceivedData object
        """
        sender = delta.get("sender", {})

        return MessageReceivedData(
            adapter_name=self.adapter_name,
            message_id=delta["message_id"],
            conversation_id=delta["conversation_id"],
            sender=SenderInfo(
                user_id=sender.get("user_id", "Unknown"),
                display_name=sender.get("display_name", "Unknown User")
            ),
            text=delta.get("text", ""),
            thread_id=delta.get("thread_id"),
            is_direct_message=delta.get("is_direct_message", True),
            attachments=[IncomingAttachmentInfo(**attachment) for attachment in delta.get("attachments", [])],
            timestamp=delta["timestamp"]
        )
