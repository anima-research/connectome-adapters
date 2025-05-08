from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

# Base models
class SenderInfo(BaseModel):
    """Model for sender information"""
    user_id: str
    display_name: str

# Data models for incoming events
class ConversationStartedData(BaseModel):
    """Conversation started event data model"""
    conversation_id: str
    history: List[Dict[str, Any]] = Field(default_factory=list)

class MessageReceivedData(BaseModel):
    """Message received event data model"""
    adapter_name: str
    message_id: str
    conversation_id: str
    sender: SenderInfo
    text: str = ""
    thread_id: Optional[str] = None
    attachments: List[Dict[str, Any]] = Field(default_factory=list)
    timestamp: int

class MessageUpdatedData(BaseModel):
    """Message updated event data model"""
    adapter_name: str
    message_id: str
    conversation_id: str
    new_text: str = ""
    timestamp: int
    attachments: List[Dict[str, Any]] = Field(default_factory=list)

class MessageDeletedData(BaseModel):
    """Message deleted event data model"""
    message_id: str
    conversation_id: str

class ReactionUpdateData(BaseModel):
    """Reaction update event data model"""
    message_id: str
    conversation_id: str
    emoji: str

class PinStatusUpdateData(BaseModel):
    """Pin status update event data model"""
    message_id: str
    conversation_id: str

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
    data: ConversationStartedData

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
