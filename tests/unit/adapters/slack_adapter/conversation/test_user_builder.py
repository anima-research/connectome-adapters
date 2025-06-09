import pytest
from unittest.mock import MagicMock

from src.adapters.slack_adapter.conversation.data_classes import ConversationInfo
from src.adapters.slack_adapter.conversation.user_builder import UserBuilder

from src.core.conversation.base_data_classes import UserInfo
from src.core.utils.config import Config

class TestUserBuilder:
    """Tests for the UserBuilder class with Slack message format"""

    @pytest.fixture
    def mock_regular_user(self):
        """Create a mock Slack user"""
        return {
            "id": "U12345678",
            "name": "test.user",
            "is_bot": False
        }

    @pytest.fixture
    def mock_bot_user(self):
        """Create a mock Slack bot user"""
        return {
            "id": "B87654321",
            "name": "testbot",
            "is_bot": True
        }

    @pytest.fixture
    def conversation_info(self):
        """Create a conversation info object"""
        return ConversationInfo(
            conversation_id="T12345/C67890",
            conversation_type="channel"
        )

    @pytest.fixture
    def slack_config(self):
        """Create a mock config object"""
        config = MagicMock(spec=Config)
        config.get_setting.return_value = "B87654321"  # The bot ID
        return config

    @pytest.mark.asyncio
    async def test_add_user_info_to_conversation_basic(self,
                                                       slack_config,
                                                       mock_regular_user,
                                                       conversation_info):
        """Test adding a regular user"""
        result = await UserBuilder.add_user_info_to_conversation(
            slack_config, mock_regular_user, conversation_info
        )

        assert result is not None
        assert result.user_id == "U12345678"
        assert result.username == "test.user"
        assert result.is_bot is False  # Regular user, not our bot

        assert "U12345678" in conversation_info.known_members
        assert conversation_info.known_members["U12345678"] is result

    @pytest.mark.asyncio
    async def test_add_user_info_to_conversation_bot(self,
                                                     slack_config,
                                                     mock_bot_user,
                                                     conversation_info):
        """Test adding a bot user"""
        result = await UserBuilder.add_user_info_to_conversation(
            slack_config, mock_bot_user, conversation_info
        )

        assert result is not None
        assert result.user_id == "B87654321"
        assert result.username == "testbot"
        assert result.is_bot is True  # Should be marked as a bot since it matches adapter_id

        assert "B87654321" in conversation_info.known_members
        assert conversation_info.known_members["B87654321"] is result

    @pytest.mark.asyncio
    async def test_add_user_info_to_conversation_existing(self,
                                                          slack_config,
                                                          mock_regular_user,
                                                          conversation_info):
        """Test adding a user that already exists"""
        existing_user = UserInfo(
            user_id="U12345678",
            username="test.user",
            is_bot=False
        )
        conversation_info.known_members["U12345678"] = existing_user

        result = await UserBuilder.add_user_info_to_conversation(
            slack_config, mock_regular_user, conversation_info
        )

        assert result is existing_user
        assert len(conversation_info.known_members) == 1

    @pytest.mark.asyncio
    async def test_add_user_info_to_conversation_invalid_user(self,
                                                              slack_config,
                                                              conversation_info):
        """Test adding invalid user data"""
        # Test with None user
        assert await UserBuilder.add_user_info_to_conversation(
            slack_config, None, conversation_info
        ) is None

        # Test with empty user object
        assert await UserBuilder.add_user_info_to_conversation(
            slack_config, {}, conversation_info
        ) is None

        # Test with user missing ID
        user_no_id = {"name": "No ID User"}
        assert await UserBuilder.add_user_info_to_conversation(
            slack_config, user_no_id, conversation_info
        ) is None
