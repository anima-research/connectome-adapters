from typing import Any, Dict, Optional

from adapters.zulip_adapter.adapter.conversation.data_classes import ConversationInfo
from core.conversation.base_data_classes import UserInfo
from core.utils.config import Config

class UserBuilder:
    """Builds user information"""

    @staticmethod
    def from_adapter(config: Config, id: str, email: str) -> bool:
        """Check if the message is from the adapter

        Args:
            config: Config object
            id: User ID
            email: User email

        Returns:
            True if the message is from the adapter, False otherwise
        """
        return (
            config.get_setting("adapter", "adapter_id") == id and
            config.get_setting("adapter", "adapter_email") == email
        )

    @staticmethod
    def add_known_members_to_private_conversation(config: Config,
                                                  message: Dict[str, Any],
                                                  conversation_info: ConversationInfo) -> None:
        """Add known members to private conversation

        Args:
            config: Config object
            message: Zulip message object
            conversation_info: Conversation info object
        """
        if len(conversation_info.known_members) > 0:
            return

        recipients = message.get("display_recipient", [])
        if not isinstance(recipients, list):
            return

        for recipient in recipients:
            user_id = str(recipient.get("id", ""))
            conversation_info.known_members[user_id] = UserInfo(
                user_id=user_id,
                username=recipient.get("full_name", None),
                email=recipient.get("email", None),
                is_bot=UserBuilder.from_adapter(config, user_id, recipient.get("email", None))
            )

    @staticmethod
    async def add_user_info_to_conversation(config: Config,
                                            message: Dict[str, Any],
                                            conversation_info: ConversationInfo) -> Optional[UserInfo]:
        """Add user info to conversation info

        Args:
            message: Zulip message object
            conversation_info: Conversation info object
            from_adapter: Whether the message is from the adapter

        Returns:
            User info object or None if user info is not found
        """
        if message.get("type", None) == "private":
            UserBuilder.add_known_members_to_private_conversation(
                config, message, conversation_info
            )

        user_id = str(message.get("sender_id", ""))
        if user_id in conversation_info.known_members:
            return conversation_info.known_members[user_id]

        if user_id:
            conversation_info.known_members[user_id] = UserInfo(
                user_id=user_id,
                username=message.get("sender_full_name", None),
                email=message.get("sender_email", None),
                is_bot=UserBuilder.from_adapter(
                    config, user_id, message.get("sender_email", None)
                )
            )
            return conversation_info.known_members[user_id]

        return None
