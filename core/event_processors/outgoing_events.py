from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any

class BaseOutgoingEvent(BaseModel):
    """Base model for all requests from the framework to adapters"""
    event_type: str
    data: Dict[str, Any]

class OutgoingAttachmentInfo(BaseModel):
    """Attachment model"""
    file_name: str
    content: str

# Data models for outgoing events
class SendMessageData(BaseModel):
    """Send message request data model"""
    conversation_id: str
    text: str
    attachments: List[OutgoingAttachmentInfo] = Field(default_factory=list)
    custom_name: Optional[str] = None  # Only used for discord webhook adapter

class EditMessageData(BaseModel):
    """Edit message request data model"""
    conversation_id: str
    message_id: str
    text: str

class DeleteMessageData(BaseModel):
    """Delete message request data model"""
    conversation_id: str
    message_id: str

class ReactionData(BaseModel):
    """Add/remove reaction request data model"""
    conversation_id: str
    message_id: str
    emoji: str

class FetchHistoryData(BaseModel):
    """Fetch history request data model"""
    conversation_id: str
    limit: Optional[int] = None
    before: Optional[int] = None
    after: Optional[int] = None

class FetchAttachmentData(BaseModel):
    """Fetch attachment request data model"""
    attachment_id: str

# Complete request models
class SendMessageEvent(BaseOutgoingEvent):
    """Complete send message event model"""
    event_type: str = "send_message"
    data: SendMessageData

class EditMessageEvent(BaseOutgoingEvent):
    """Complete edit message event model"""
    event_type: str = "edit_message"
    data: EditMessageData

class DeleteMessageEvent(BaseOutgoingEvent):
    """Complete delete message event model"""
    event_type: str = "delete_message"
    data: DeleteMessageData

class AddReactionEvent(BaseOutgoingEvent):
    """Complete add reaction event model"""
    event_type: str = "add_reaction"
    data: ReactionData

class RemoveReactionEvent(BaseOutgoingEvent):
    """Complete remove reaction event model"""
    event_type: str = "remove_reaction"
    data: ReactionData

class FetchHistoryEvent(BaseOutgoingEvent):
    """Complete fetch history event model"""
    event_type: str = "fetch_history"
    data: FetchHistoryData

class FetchAttachmentEvent(BaseOutgoingEvent):
    """Complete fetch attachment event model"""
    event_type: str = "fetch_attachment"
    data: FetchAttachmentData
