from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any

class BaseEvent(BaseModel):
    """Base model for all requests from the framework to adapters"""
    event_type: str
    data: Dict[str, Any]

# Data models for outgoing events
class FileData(BaseModel):
    """Request data model shared between view, delete and undo"""
    path: str

class ContentData(BaseModel):
    """Request data model shared between create and update"""
    path: str
    content: str

class ReadData(BaseModel):
    """Read request data model"""
    path: str
    line_range: Optional[List[int]] = None

class MoveData(BaseModel):
    """Move request data model"""
    source_path: str
    destination_path: str

class InsertData(BaseModel):
    """Insert request data model"""
    path: str
    content: str
    line: int

class ReplaceData(BaseModel):
    """Replace request data model"""
    path: str
    old_string: str
    new_string: str

# Complete request models
class ViewEvent(BaseEvent):
    """Complete view event model"""
    event_type: str = "send_message"
    data: FileData

class ReadEvent(BaseEvent):
    """Complete view event model"""
    event_type: str = "read"
    data: ReadData

class CreateEvent(BaseEvent):
    """Complete create event model"""
    event_type: str = "create"
    data: ContentData

class DeleteEvent(BaseEvent):
    """Complete delete event model"""
    event_type: str = "delete"
    data: FileData

class MoveEvent(BaseEvent):
    """Complete move event model"""
    event_type: str = "move"
    data: MoveData

class UpdateEvent(BaseEvent):
    """Complete update event model"""
    event_type: str = "update"
    data: ContentData

class InsertEvent(BaseEvent):
    """Complete insert event model"""
    event_type: str = "insert"
    data: InsertData

class ReplaceEvent(BaseEvent):
    """Complete replace event model"""
    event_type: str = "replace"
    data: ReplaceData

class UndoEvent(BaseEvent):
    """Complete undo event model"""
    event_type: str = "undo"
    data: FileData

class OutgoingEventBuilder:
    """Builder class for outgoing events"""

    def build(self, data: Dict[str, Any]) -> BaseEvent:
        """Build the event based on the event type

        Args:
            data: The data to build the event from

        Returns:
            The built event
        """
        event_type = data.get("event_type", None)
        event_data = data.get("data", {})

        if event_type == "view":
            return ViewEvent(event_type=event_type, data=FileData(**event_data))

        if event_type == "read":
            return ReadEvent(event_type=event_type, data=ReadData(**event_data))

        if event_type == "create":
            return CreateEvent(event_type=event_type, data=ContentData(**event_data))

        if event_type == "delete":
            return DeleteEvent(event_type=event_type, data=FileData(**event_data))

        if event_type == "move":
            return MoveEvent(event_type=event_type, data=MoveData(**event_data))

        if event_type == "update":
            return UpdateEvent(event_type=event_type, data=ContentData(**event_data))

        if event_type == "insert":
            return InsertEvent(event_type=event_type, data=InsertData(**event_data))

        if event_type == "replace":
            return ReplaceEvent(event_type=event_type, data=ReplaceData(**event_data))

        if event_type == "undo":
            return UndoEvent(event_type=event_type, data=FileData(**event_data))

        raise ValueError(f"Unknown event type: {event_type}")
