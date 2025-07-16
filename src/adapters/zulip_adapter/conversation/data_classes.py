from dataclasses import dataclass, field
from typing import Optional, List, Set

from src.core.cache.cache import Cache
from src.core.conversation.base_data_classes import BaseConversationInfo

@dataclass
class ConversationInfo(BaseConversationInfo):
    """Comprehensive information about a Zulip conversation"""
    stream_id: Optional[str] = ""
    stream_name: Optional[str] = ""
    stream_topic: Optional[str] = ""
    messages: Set[str] = field(default_factory=set)

    def set_stream_conversation_name(self) -> None:
        """Set the stream conversation name"""
        if self.stream_name and self.stream_topic:
            self.conversation_name = "_".join([self.stream_name, self.stream_topic])

    def emails(self) -> List[str]:
        """Get the emails for the conversation"""
        emails = []
        user_cache = Cache.get_instance().user_cache

        for user_id in self.known_members:
            user_info = user_cache.get_user_by_id(user_id)
            if user_info and user_info.email:
                emails.append(user_info.email)

        return emails
