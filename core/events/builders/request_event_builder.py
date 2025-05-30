from typing import Any, Dict, Optional

from core.events.models.incoming_events import IncomingAttachmentInfo, SenderInfo
from core.events.models.request_events import (
    RequestEvent,
    FetchedAttachmentData,
    FetchedMessageData,
    HistoryData,
    SentMessageData,
    ReadFileData,
    ViewDirectoryData
)

class RequestEventBuilder:
    """Builder class for request events"""
    def __init__(self, adapter_type: str):
        """Initialize the builder with the data"""
        self.adapter_type = adapter_type

    def build(self,
              request_id: str,
              internal_request_id: Optional[str] = None,
              data: Optional[Dict[str, Any]] = {}) -> RequestEvent:
        """Build the event based on the event type

        Args:
            request_id: The request ID
            internal_request_id: The internal request ID
            data: The data to build the event from

        Returns:
            The request event
        """
        validated_data = None

        if "message_ids" in data:
            validated_data = SentMessageData(message_ids=data["message_ids"])
        elif "content" in data:
            validated_data = FetchedAttachmentData(content=data["content"])
        elif "history" in data:
            history = []
            for message in data["history"]:
                attachments = [IncomingAttachmentInfo(**attachment) for attachment in message.get("attachments", [])]
                history.append(
                    FetchedMessageData(
                        message_id=message.get("message_id", None),
                        conversation_id=message.get("conversation_id", None),
                        sender=SenderInfo(
                            user_id=message.get("sender", {}).get("user_id", "Unknown"),
                            display_name=message.get("sender", {}).get("display_name", "Unknown User")
                        ),
                        text=message.get("text", ""),
                        thread_id=message.get("thread_id"),
                        attachments=attachments,
                        timestamp=message.get("timestamp", None)
                    )
                )
            validated_data = HistoryData(history=history)
        elif "file_content" in data:
            validated_data = ReadFileData(file_content=data["file_content"])
        elif "directories" in data:
            validated_data = ViewDirectoryData(directories=data["directories"], files=data["files"])

        return RequestEvent(
            adapter_type=self.adapter_type,
            request_id=request_id,
            internal_request_id=internal_request_id,
            data=validated_data
        )
