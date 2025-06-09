from typing import Any, Optional

from src.adapters.discord_adapter.conversation.data_classes import ConversationInfo
from src.core.conversation.base_data_classes import UserInfo
from src.core.utils.config import Config

class UserBuilder:
    """Builds user information from Discord messages"""

    @staticmethod
    async def add_user_info_to_conversation(config: Config,
                                            message: Any,
                                            conversation_info: ConversationInfo) -> Optional[UserInfo]:
        """Add user info to conversation info

        Args:
            config: Config instance
            message: Discord message object
            conversation_info: Conversation info object

        Returns:
            User info object or None if user info is not found
        """
        if not message or not hasattr(message, "author") or not message.author:
            return None

        user = message.author
        user_id = str(user.id)

        if not user_id:
            return None

        if user_id in conversation_info.known_members:
            return conversation_info.known_members[user_id]

        conversation_info.known_members[user_id] = UserInfo(
            user_id=user_id,
            username=user.name,
            is_bot=config.get_setting("adapter", "adapter_id") == user_id
        )
        return conversation_info.known_members[user_id]
