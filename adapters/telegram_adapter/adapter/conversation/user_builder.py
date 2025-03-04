from typing import Any, Optional

from adapters.telegram_adapter.adapter.conversation.data_classes import ConversationInfo
from core.conversation.base_data_classes import UserInfo

class UserBuilder:
    """Builds user information"""

    @staticmethod
    async def add_user_info_to_conversation(user: Any,
                                            conversation_info: ConversationInfo) -> Optional[UserInfo]:
        """Add user info to conversation info

        Args:
            user: Telethon user object
            conversation_info: Conversation info object

        Returns:
            User info object or None if user is not found
        """
        if not user:
            return {}

        user_id = str(getattr(user, "id", ""))
        if not user_id:
            return {}

        if user_id in conversation_info.known_members:
            return conversation_info.known_members[user_id]

        user_info = UserInfo(user_id=user_id)
        user_info.username = getattr(user, "username", None)
        user_info.first_name = getattr(user, "first_name", "Unknown")
        user_info.last_name = getattr(user, "last_name", "Unknown")
        user_info.is_bot = getattr(user, "bot", False)
        conversation_info.known_members[user_id] = user_info

        return user_info
