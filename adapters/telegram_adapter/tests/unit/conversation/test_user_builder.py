import pytest
from unittest.mock import MagicMock

from adapters.telegram_adapter.adapter.conversation.data_classes import ConversationInfo
from adapters.telegram_adapter.adapter.conversation.user_builder import UserBuilder
from core.conversation.base_data_classes import ConversationDelta, UserInfo

class TestUserBuilder:
    """Tests for the UserBuilder class"""

    @pytest.fixture
    def mock_user(self):
        """Create a mock Telethon user"""
        user = MagicMock()
        user.id = 123
        user.username = "testuser"
        user.first_name = "Test"
        user.last_name = "User"
        user.bot = False
        return user

    @pytest.fixture
    def conversation_info(self):
        """Create a conversation info object"""
        return ConversationInfo(
            conversation_id="789",
            conversation_type="private"
        )

    @pytest.mark.asyncio
    async def test_add_user_info_new_user(self, mock_user, conversation_info):
        """Test adding a new user to conversation info"""
        assert len(conversation_info.known_members) == 0

        await UserBuilder.add_user_info_to_conversation(mock_user, conversation_info)
        assert "123" in conversation_info.known_members

        user_info = conversation_info.known_members["123"]
        assert user_info.user_id == "123"
        assert user_info.username == "testuser"
        assert user_info.first_name == "Test"
        assert user_info.last_name == "User"
        assert user_info.is_bot is False

    @pytest.mark.asyncio
    async def test_add_user_info_existing_user(self, mock_user, conversation_info):
        """Test adding an existing user to conversation info"""
        user_info = UserInfo(str(mock_user.id))
        user_info.username = mock_user.username
        user_info.first_name = mock_user.first_name
        user_info.last_name = mock_user.last_name
        user_info.is_bot = mock_user.bot
        conversation_info.known_members[str(mock_user.id)] = user_info

        await UserBuilder.add_user_info_to_conversation(mock_user, conversation_info)
        assert len(conversation_info.known_members) == 1

    @pytest.mark.asyncio
    async def test_add_user_info_none(self, conversation_info):
        """Test adding a None user to conversation info"""
        await UserBuilder.add_user_info_to_conversation(None, conversation_info)
        assert len(conversation_info.known_members) == 0
