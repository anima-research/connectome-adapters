from pydantic import BaseModel
from typing import Any, Dict, Optional

class BaseEvent(BaseModel):
    """Base model for all requests from the framework to adapters"""
    event_type: str
    data: Optional[Dict[str, Any]] = {}

# Data models for outgoing events
class SessionData(BaseModel):
    """Session request data model used for closing a session"""
    session_id: str

class CommandData(BaseModel):
    """Command request data model used for executing a command"""
    command: str
    session_id: Optional[str] = None

# Complete request models
class OpenSessionEvent(BaseEvent):
    """Complete open session event model"""
    event_type: str = "open_session"
    data: Optional[Dict[str, Any]] = {}

class CloseSessionEvent(BaseEvent):
    """Complete close session event model"""
    event_type: str = "close_session"
    data: SessionData

class ExecuteCommandEvent(BaseEvent):
    """Complete execute command event model"""
    event_type: str = "execute_command"
    data: CommandData

class ShellMetadataEvent(BaseEvent):
    """Complete shell metadata event model"""
    event_type: str = "shell_metadata"
    data: Optional[Dict[str, Any]] = {}

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

        if event_type == "open_session":
            return OpenSessionEvent(event_type=event_type, data=event_data)

        if event_type == "close_session":
            return CloseSessionEvent(event_type=event_type, data=SessionData(**event_data))

        if event_type == "execute_command":
            return ExecuteCommandEvent(event_type=event_type, data=CommandData(**event_data))

        if event_type == "shell_metadata":
            return ShellMetadataEvent(event_type=event_type, data=event_data)

        raise ValueError(f"Unknown event type: {event_type}")
