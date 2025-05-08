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
    def __init__(self, data: Dict[str, Any]):
        """Initialize the builder with the data"""
        self.event_type = data.get("event_type", None)
        self.data = data.get("data", {})

    def build(self) -> BaseEvent:
        """Build the event based on the event type"""
        if self.event_type == "view":
            validated_data = FileData(**self.data)
            return ViewEvent(event_type=self.event_type, data=validated_data)

        if self.event_type == "read":
            validated_data = ReadData(**self.data)
            return ReadEvent(event_type=self.event_type, data=validated_data)

        if self.event_type == "create":
            validated_data = ContentData(**self.data)
            return CreateEvent(event_type=self.event_type, data=validated_data)

        if self.event_type == "delete":
            validated_data = FileData(**self.data)
            return DeleteEvent(event_type=self.event_type, data=validated_data)

        if self.event_type == "move":
            validated_data = MoveData(**self.data)
            return MoveEvent(event_type=self.event_type, data=validated_data)

        if self.event_type == "update":
            validated_data = ContentData(**self.data)
            return UpdateEvent(event_type=self.event_type, data=validated_data)

        if self.event_type == "insert":
            validated_data = InsertData(**self.data)
            return InsertEvent(event_type=self.event_type, data=validated_data)

        if self.event_type == "replace":
            validated_data = ReplaceData(**self.data)
            return ReplaceEvent(event_type=self.event_type, data=validated_data)

        if self.event_type == "undo":
            validated_data = FileData(**self.data)
            return UndoEvent(event_type=self.event_type, data=validated_data)

        raise ValueError(f"Unknown event type: {self.event_type}")
