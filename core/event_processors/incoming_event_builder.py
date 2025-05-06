
from typing import Any, Dict, List, Union

class IncomingEventBuilder:
    """
    Event builder for constructing standardized events to send to the framework.
    This class handles the construction of properly formatted event dictionaries
    while providing documentation and validation.
    """

    def __init__(self, adapter_type: str, adapter_name: str):
        """
        Initialize the EventBuilder with the adapter type.

        Args:
            adapter_type: The adapter type (telegram, discord, etc.)
            adapter_name: Name of the adapter instance
        """
        self.adapter_type = adapter_type
        self.adapter_name = adapter_name

    def conversation_started(self,
                             delta: Dict[str, Any],
                             history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Create a conversation_started event.

        Args:
            delta: Event change information
            history: List of message history items

        Returns:
            Dictionary containing the event in the standard format:
            {
                "adapter_type": str,
                "event_type": "conversation_started",
                "data": {
                    "conversation_id": str,
                    "history": List[Dict]
                }
            }
        """
        return {
            "adapter_type": self.adapter_type,
            "event_type": "conversation_started",
            "data": {
                "conversation_id": delta["conversation_id"],
                "history": history
            }
        }

    def message_received(self, delta: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a message_received event.

        Args:
            delta: Event change information

        Returns:
            Dictionary containing the event in the standard format:
            {
                "adapter_type": str,
                "event_type": "message_received",
                "data": {
                    "adapter_name": str,
                    "message_id": str,
                    "conversation_id": str,
                    "sender": {
                        "user_id": str,
                        "display_name": str
                    },
                    "text": str,
                    "thread_id": Optional[str],
                    "attachments": List[Dict],
                    "timestamp": int
                }
            }
        """
        return {
            "adapter_type": self.adapter_type,
            "event_type": "message_received",
            "data": {
                "adapter_name": self.adapter_name,
                "message_id": delta["message_id"],
                "conversation_id": delta["conversation_id"],
                "sender": {
                    "user_id": delta["sender"]["user_id"] if "sender" in delta else "Unknown",
                    "display_name": delta["sender"]["display_name"] if "sender" in delta else "Unknown User"
                },
                "text": delta["text"] if "text" in delta else "",
                "thread_id": delta["thread_id"] if "thread_id" in delta else None,
                "attachments": delta["attachments"] if "attachments" in delta else [],
                "timestamp": delta["timestamp"]  # in milliseconds
            }
        }

    def message_updated(self, delta: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a message_updated event.

        Args:
            delta: Event change information

        Returns:
            Dictionary containing the event in the standard format:
            {
                "adapter_type": str,
                "event_type": "message_updated",
                "data": {
                    "adapter_name": str,
                    "message_id": str,
                    "conversation_id": str,
                    "new_text": str,
                    "attachments": List[Dict],
                    "timestamp": int
                }
            }
        """
        return {
            "adapter_type": self.adapter_type,
            "event_type": "message_updated",
            "data": {
                "adapter_name": self.adapter_name,
                "message_id": delta["message_id"],
                "conversation_id": delta["conversation_id"],
                "new_text": delta["text"] if "text" in delta else "",
                "timestamp": delta["timestamp"],
                "attachments": delta["attachments"] if "attachments" in delta else []
            }
        }

    def message_deleted(self, message_id: Union[int, str], conversation_id: Union[int, str]) -> Dict[str, Any]:
        """
        Create a message_deleted event.

        Args:
            message_id: ID of the deleted message
            conversation_id: ID of the conversation

        Returns:
            Dictionary containing the event in the standard format:
            {
                "adapter_type": str,
                "event_type": "message_deleted",
                "data": {
                    "message_id": str,
                    "conversation_id": str
                }
            }
        """
        return {
            "adapter_type": self.adapter_type,
            "event_type": "message_deleted",
            "data": {
                "message_id": str(message_id),
                "conversation_id": str(conversation_id)
            }
        }

    def reaction_update(self,
                        event_type: str,
                        delta: Dict[str, Any],
                        reaction: str) -> Dict[str, Any]:
        """
        Create a reaction_update event.

        Args:
            event_type: Type of reaction event (added/removed)
            delta: Event change information
            reaction: Emoji reaction
        Returns:
            Dictionary containing the event in the standard format:
            {
                "adapter_type": str,
                "event_type": event_type, # reaction_added or reaction_removed
                "data": {
                    "message_id": str,
                    "conversation_id": str,
                    "emoji": str
                }
            }
        """
        return {
            "adapter_type": self.adapter_type,
            "event_type": event_type,
            "data": {
                "message_id": delta["message_id"],
                "conversation_id": delta["conversation_id"],
                "emoji": reaction
            }
        }

    def pin_status_update(self, event_type: str, delta: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a message_pinned event.

        Args:
            event_type: Type of pin event (pinned/unpinned)
            delta: Event change information

        Returns:
            Dictionary containing the event in the standard format:
            {
                "adapter_type": str,
                "event_type": event_type, # message_pinned or message_unpinned
                "data": {
                    "message_id": str,
                    "conversation_id": str,
                }
            }
        """
        return {
            "adapter_type": self.adapter_type,
            "event_type": event_type,
            "data": {
                "message_id": delta["message_id"],
                "conversation_id": delta["conversation_id"],
            }
        }
