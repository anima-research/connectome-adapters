from dataclasses import dataclass, field
from typing import Optional, List, Set, Union

from src.core.conversation.base_data_classes import BaseConversationInfo

@dataclass
class ConversationInfo(BaseConversationInfo):
    """Comprehensive information about a Zulip conversation"""
    messages: Set[str] = field(default_factory=set)

    def _private_to_fields(self) -> List[str]:
        """Get the private to fields for the conversation"""
        emails = []
        for _, user_info in self.known_members.items():
            if user_info.email:
                emails.append(user_info.email)
        return emails

    def _stream_to_fields(self) -> Optional[str]:
        """Get the stream to fields for the conversation"""
        return self.conversation_name

    def to_fields(self) -> Optional[Union[List[str], str]]:
        """Get the to fields for the conversation"""
        if self.conversation_type == "private":
            return self._private_to_fields()
        return self._stream_to_fields()
