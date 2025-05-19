from typing import Any, Dict
from core.event_processors.outgoing_events import (
    OutgoingAttachmentInfo,
    SendMessageData,
    EditMessageData,
    DeleteMessageData,
    ReactionData,
    FetchHistoryData,
    FetchAttachmentData,
    PinStatusData,
    BaseOutgoingEvent,
    SendMessageEvent,
    EditMessageEvent,
    DeleteMessageEvent,
    AddReactionEvent,
    RemoveReactionEvent,
    FetchHistoryEvent,
    FetchAttachmentEvent,
    PinMessageEvent,
    UnpinMessageEvent
)

class OutgoingEventBuilder:
    """Builder class for outgoing events"""

    def build(self, data: Dict[str, Any]) -> BaseOutgoingEvent:
        """Build the event based on the event type

        Args:
            data: The data to build the event from

        Returns:
            The built event
        """
        event_type = data.get("event_type", None)
        event_data = data.get("data", {})

        if event_type == "send_message":
            attachments = [OutgoingAttachmentInfo(**attachment) for attachment in event_data.get("attachments", [])]
            return SendMessageEvent(
                event_type=event_type,
                data=SendMessageData(
                    conversation_id=event_data.get("conversation_id", None),
                    text=event_data.get("text", None),
                    thread_id=event_data.get("thread_id", None),
                    custom_name=event_data.get("custom_name", None),
                    mentions=event_data.get("mentions", []),
                    attachments=attachments
                )
            )

        if event_type == "edit_message":
            return EditMessageEvent(
                event_type=event_type,
                data=EditMessageData(**event_data)
            )

        if event_type == "delete_message":
            return DeleteMessageEvent(
                event_type=event_type,
                data=DeleteMessageData(**event_data)
            )

        if event_type == "add_reaction":
            return AddReactionEvent(
                event_type=event_type,
                data=ReactionData(**event_data)
            )

        if event_type == "remove_reaction":
            return RemoveReactionEvent(
                event_type=event_type,
                data=ReactionData(**event_data)
            )

        if event_type == "fetch_history":
            return FetchHistoryEvent(
                event_type=event_type,
                data=FetchHistoryData(**event_data)
            )

        if event_type == "fetch_attachment":
            return FetchAttachmentEvent(
                event_type=event_type,
                data=FetchAttachmentData(**event_data)
            )

        if event_type == "pin_message":
            return PinMessageEvent(
                event_type=event_type,
                data=PinStatusData(**event_data)
            )

        if event_type == "unpin_message":
            return UnpinMessageEvent(
                event_type=event_type,
                data=PinStatusData(**event_data)
            )

        raise ValueError(f"Unknown event type: {event_type}")
