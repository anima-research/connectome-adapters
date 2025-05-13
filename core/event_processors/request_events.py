from pydantic import BaseModel, Field
from typing import List, Optional, Union
from core.event_processors.incoming_events import IncomingAttachmentInfo, SenderInfo

class SentMessageData(BaseModel):
    """Sent message data model"""
    message_ids: List[str]

class FetchedAttachmentData(BaseModel):
    """Fetched attachment data model"""
    content: str

class FetchedMessageData(BaseModel):
    """Fetched message data model"""
    message_id: str
    conversation_id: str
    sender: SenderInfo
    text: str = ""
    thread_id: Optional[str] = None
    is_direct_message: bool = True
    attachments: List[IncomingAttachmentInfo] = Field(default_factory=list)
    timestamp: int

class HistoryData(BaseModel):
    """History data model"""
    history: List[FetchedMessageData] = Field(default_factory=list)

class RequestEvent(BaseModel):
    """Request event model"""
    adapter_type: str
    request_id: str
    data: Optional[Union[SentMessageData, HistoryData, FetchedAttachmentData]] = None
