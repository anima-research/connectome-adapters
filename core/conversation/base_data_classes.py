from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List, Set, Union

class ConversationUpdateType(str, Enum):
    """Types of updates that can occur in a conversation"""
    CONVERSATION_STARTED = "conversation_started"
    MESSAGE_RECEIVED = "message_received"
    MESSAGE_EDITED = "message_edited"
    REACTION_ADDED = "reaction_added"
    REACTION_REMOVED = "reaction_removed"
    MESSAGE_PINNED = "message_pinned"
    MESSAGE_UNPINNED = "message_unpinned"

@dataclass
class UserInfo:
    """Information about a user"""
    user_id: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None
    email: Optional[str] = None
    is_bot: bool = False

    @property
    def mention(self) -> str:
        """Get a mention string for the user"""
        if self.username:
            return f"@{self.username}"
        return f"User {self.user_id}"

    @property
    def display_name(self) -> str:
        """Get a human-readable display name"""
        if self.username:
            return f"{self.username}"

        name_parts = []
        if self.first_name:
            name_parts.append(self.first_name)
        if self.last_name:
            name_parts.append(self.last_name)
        if name_parts:
            return " ".join(name_parts)

        if self.email:
            return self.email

        return f"User {self.user_id}"

@dataclass
class ThreadInfo:
    """Information about a thread within a conversation"""
    thread_id: str  # Could be message_thread_id, reply message_id, etc.
    title: Optional[str] = None  # For named threads/topics
    root_message_id: Optional[str] = None  # ID of the message that started the thread
    last_activity: datetime = None
    messages: Set[str] = field(default_factory=set)

    def __post_init__(self):
        if self.last_activity is None:
            self.last_activity = datetime.now()

@dataclass
class BaseConversationInfo:
    """Comprehensive information about a conversation"""
    # Core identifiers
    conversation_id: str
    conversation_type: str  # depends on the adapter (for example, in Zulip it is either "private" or "stream")
    conversation_name: Optional[str] = None

    # Activity tracking
    created_at: datetime = None  # When we first saw this chat
    last_activity: datetime = None  # Last message times

    # Metadata storage
    known_members: Dict[str, UserInfo] = field(default_factory=dict)
    just_started: bool = False

    # Add thread tracking
    threads: Dict[str, ThreadInfo] = field(default_factory=dict)

    # Add attachment tracking
    attachments: Set[str] = field(default_factory=set)

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.last_activity is None:
            self.last_activity = datetime.now()

@dataclass
class ConversationDelta:
    """Changes in conversation state"""
    conversation_id: str
    message_id: Optional[str] = None
    fetch_history: bool = False
    display_bot_messages: bool = False
    added_reactions: List[str] = field(default_factory=list)
    removed_reactions: List[str] = field(default_factory=list)
    deleted_message_ids: List[str] = field(default_factory=list)
    added_messages: List[Dict[str, Any]] = field(default_factory=list)
    updated_messages: List[Dict[str, Any]] = field(default_factory=list)
    pinned_message_ids: List[str] = field(default_factory=list)
    unpinned_message_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        result = {
            "conversation_id": self.conversation_id,
            "fetch_history": self.fetch_history
        }

        if self.message_id:
            result["message_id"] = self.message_id
        if self.added_reactions:
            result["added_reactions"] = self.added_reactions
        if self.removed_reactions:
            result["removed_reactions"] = self.removed_reactions
        if self.deleted_message_ids:
            result["deleted_message_ids"] = self.deleted_message_ids
        if self.added_messages:
            result["added_messages"] = self.added_messages
        if self.updated_messages:
            result["updated_messages"] = self.updated_messages
        if self.pinned_message_ids:
            result["pinned_message_ids"] = self.pinned_message_ids
        if self.unpinned_message_ids:
            result["unpinned_message_ids"] = self.unpinned_message_ids

        return result
