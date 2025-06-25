from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

# Base models
class SenderInfo(BaseModel):
    """Model for sender information"""
    user_id: str
    display_name: str

class IncomingAttachmentInfo(BaseModel):
    """Model for attachment information"""
    attachment_id: str
    filename: str
    size: int
    processable: bool
    content_type: Optional[str] = None
    content: Optional[str] = None
    url: Optional[str] = None

# Data models for incoming events
class BaseIncomingData(BaseModel):
    """Base data model for incoming events"""
    adapter_name: str
    adapter_id: str

class MessageReceivedData(BaseIncomingData):
    """Message received event data model"""
    message_id: str
    conversation_id: str
    sender: SenderInfo
    timestamp: int
    edited: bool
    is_direct_message: bool
    text: Optional[str] = ""
    thread_id: Optional[str] = None
    attachments: Optional[List[IncomingAttachmentInfo]] = Field(default_factory=list)
    mentions: Optional[List[str]] = Field(default_factory=list)
    edit_timestamp: Optional[int] = None

class MessageUpdatedData(BaseIncomingData):
    """Message updated event data model"""
    message_id: str
    conversation_id: str
    new_text: str = ""
    timestamp: Optional[int] = None
    attachments: List[IncomingAttachmentInfo] = Field(default_factory=list)
    mentions: Optional[List[str]] = Field(default_factory=list)

class MessageDeletedData(BaseIncomingData):
    """Message deleted event data model"""
    message_id: str
    conversation_id: str

class ReactionUpdateData(BaseIncomingData):
    """Reaction update event data model"""
    message_id: str
    conversation_id: str
    emoji: str

class PinStatusUpdateData(BaseIncomingData):
    """Pin status update event data model"""
    message_id: str
    conversation_id: str

class ConversationMetaData(BaseIncomingData):
    """Conversation metadata model"""
    conversation_id: str
    conversation_name: Optional[str] = None
    server_name: Optional[str] = None

class HistoryFetchedData(BaseIncomingData):
    """History fetched event data model"""
    conversation_id: str
    history: List[MessageReceivedData] = Field(default_factory=list)

# Base incoming event model
class BaseIncomingEvent(BaseModel):
    """Base model for all events sent to the framework"""
    adapter_type: str
    event_type: str
    data: Dict[str, Any]

# Specific event models
class ConversationStartedEvent(BaseIncomingEvent):
    """Conversation started event model"""
    event_type: str = "conversation_started"
    data: ConversationMetaData

class ConversationUpdatedEvent(BaseIncomingEvent):
    """Conversation updated event model"""
    event_type: str = "conversation_updated"
    data: ConversationMetaData

class MessageReceivedEvent(BaseIncomingEvent):
    """Message received event model"""
    event_type: str = "message_received"
    data: MessageReceivedData

class MessageUpdatedEvent(BaseIncomingEvent):
    """Message updated event model"""
    event_type: str = "message_updated"
    data: MessageUpdatedData

class MessageDeletedEvent(BaseIncomingEvent):
    """Message deleted event model"""
    event_type: str = "message_deleted"
    data: MessageDeletedData

class ReactionAddedEvent(BaseIncomingEvent):
    """Reaction added event model"""
    event_type: str = "reaction_added"
    data: ReactionUpdateData

class ReactionRemovedEvent(BaseIncomingEvent):
    """Reaction removed event model"""
    event_type: str = "reaction_removed"
    data: ReactionUpdateData

class MessagePinnedEvent(BaseIncomingEvent):
    """Message pinned event model"""
    event_type: str = "message_pinned"
    data: PinStatusUpdateData

class MessageUnpinnedEvent(BaseIncomingEvent):
    """Message unpinned event model"""
    event_type: str = "message_unpinned"
    data: PinStatusUpdateData

class HistoryFetchedEvent(BaseIncomingEvent):
    """History fetched event model"""
    event_type: str = "history_fetched"
    data: HistoryFetchedData
