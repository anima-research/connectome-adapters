from typing import Any, Dict, Optional
from src.core.events.models.request_events import (
    RequestEvent,
    FetchedAttachmentData,
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
