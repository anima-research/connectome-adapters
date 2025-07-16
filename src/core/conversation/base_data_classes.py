import random
import string
import time

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List, Set

from src.core.cache.user_cache import UserInfo

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
    platform_conversation_id: str
    conversation_type: str  # depends on the adapter (for example, in Zulip it is either "private" or "stream")
    conversation_name: Optional[str] = None
    server_id: Optional[str] = None
    server_name: Optional[str] = None

    # Activity tracking
    created_at: datetime = None  # When we first saw this chat
    last_activity: datetime = None  # Last message times

    # Metadata storage
    known_members: Set[str] = field(default_factory=set)
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
    conversation_name: Optional[str] = None
    server_name: Optional[str] = None
    message_id: Optional[str] = None
    fetch_history: bool = False
    history_fetching_in_progress: bool = False
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
            "conversation_name": self.conversation_name,
            "server_name": self.server_name,
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
