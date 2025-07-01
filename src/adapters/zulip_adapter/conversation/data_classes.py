from dataclasses import dataclass, field
from typing import Optional, List, Set, Union

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
        for _, user_info in self.known_members.items():
            if user_info.email:
                emails.append(user_info.email)
        return emails
