from typing import Any, Dict
from core.event_processors.outgoing_events import (
    SendMessageData,
    EditMessageData,
    DeleteMessageData,
    ReactionData,
    FetchHistoryData,
    BaseOutgoingEvent,
    SendMessageEvent,
    EditMessageEvent,
    DeleteMessageEvent,
    AddReactionEvent,
    RemoveReactionEvent,
    FetchHistoryEvent
)

class OutgoingEventBuilder:
    """Builder class for outgoing events"""
    def __init__(self, data: Dict[str, Any]):
        """Initialize the builder with the data"""
        self.event_type = data.get("event_type", None)
        self.data = data.get("data", {})

    def build(self) -> BaseOutgoingEvent:
        """Build the event based on the event type"""
        if self.event_type == "send_message":
            validated_data = SendMessageData(**self.data)
            return SendMessageEvent(event_type=self.event_type, data=validated_data)

        if self.event_type == "edit_message":
            validated_data = EditMessageData(**self.data)
            return EditMessageEvent(event_type=self.event_type, data=validated_data)

        if self.event_type == "delete_message":
            validated_data = DeleteMessageData(**self.data)
            return DeleteMessageEvent(event_type=self.event_type, data=validated_data)

        if self.event_type == "add_reaction":
            validated_data = ReactionData(**self.data)
            return AddReactionEvent(event_type=self.event_type, data=validated_data)

        if self.event_type == "remove_reaction":
            validated_data = ReactionData(**self.data)
            return RemoveReactionEvent(event_type=self.event_type, data=validated_data)

        if self.event_type == "fetch_history":
            validated_data = FetchHistoryData(**self.data)
            return FetchHistoryEvent(event_type=self.event_type, data=validated_data)

        raise ValueError(f"Unknown event type: {self.event_type}")
