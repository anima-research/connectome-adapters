from typing import Any, Dict
from core.event_processors.outgoing_events import (
    OutgoingAttachmentInfo,
    SendMessageData,
    EditMessageData,
    DeleteMessageData,
    ReactionData,
    FetchHistoryData,
    FetchAttachmentData,
    BaseOutgoingEvent,
    SendMessageEvent,
    EditMessageEvent,
    DeleteMessageEvent,
    AddReactionEvent,
    RemoveReactionEvent,
    FetchHistoryEvent,
    FetchAttachmentEvent
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
            attachments = [OutgoingAttachmentInfo(**attachment) for attachment in self.data.get("attachments", [])]
            validated_data = SendMessageData(
                conversation_id=self.data.get("conversation_id", None),
                text=self.data.get("text", None),
                custom_name=self.data.get("custom_name", None),
                attachments=attachments
            )
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

        if self.event_type == "fetch_attachment":
            validated_data = FetchAttachmentData(**self.data)
            return FetchAttachmentEvent(event_type=self.event_type, data=validated_data)

        raise ValueError(f"Unknown event type: {self.event_type}")
