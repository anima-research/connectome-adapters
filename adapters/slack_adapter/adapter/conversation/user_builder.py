from typing import Any, Optional

from adapters.slack_adapter.adapter.conversation.data_classes import ConversationInfo
from core.conversation.base_data_classes import UserInfo
from core.utils.config import Config

class UserBuilder:
    """Builds user information from Slack messages"""

    @staticmethod
    async def add_user_info_to_conversation(config: Config,
                                            user: Any,
                                            conversation_info: ConversationInfo) -> Optional[UserInfo]:
        """Add user info to conversation info

        Args:
            config: Config instance
            user: Slack user object
            conversation_info: Conversation info object

        Returns:
            User info object or None if user info is not found
        """
        if not user:
            return None

        user_id = str(user.get("id", ""))
        if not user_id:
            return None

        if user_id in conversation_info.known_members:
            return conversation_info.known_members[user_id]

        conversation_info.known_members[user_id] = UserInfo(
            user_id=user_id,
            username=str(user.get("name", "")),
            is_bot=config.get_setting("adapter", "adapter_id") == user_id
        )
        return conversation_info.known_members[user_id]
