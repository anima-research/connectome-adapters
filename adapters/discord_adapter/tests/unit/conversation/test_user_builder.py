import pytest
from unittest.mock import MagicMock, patch

from adapters.discord_adapter.adapter.conversation.data_classes import ConversationInfo
from adapters.discord_adapter.adapter.conversation.user_builder import UserBuilder

from core.conversation.base_data_classes import UserInfo
from core.utils.config import Config

class TestUserBuilder:
    """Tests for the UserBuilder class with Discord message format"""

    @pytest.fixture
    def mock_author(self):
        """Create a mock Discord author"""
        author = MagicMock()
        author.id = 123
        author.name = "Test User"
        return author

    @pytest.fixture
    def mock_bot_author(self):
        """Create a mock Discord bot author"""
        author = MagicMock()
        author.id = 12345
        author.name = "Bot User"
        return author

    @pytest.fixture
    def mock_message(self, mock_author):
        """Create a mock Discord message"""
        message = MagicMock()
        message.author = mock_author
        return message

    @pytest.fixture
    def mock_bot_message(self, mock_bot_author):
        """Create a mock Discord message from a bot"""
        message = MagicMock()
        message.author = mock_bot_author
        return message

    @pytest.fixture
    def conversation_info(self):
        """Create a conversation info object"""
        return ConversationInfo(
            conversation_id="123456789",
            conversation_type="text_channel"
        )

    @pytest.mark.asyncio
    async def test_add_user_info_to_conversation_basic(self,
                                                       patch_config,
                                                       mock_message,
                                                       conversation_info):
        """Test adding a user from a basic message"""
        result = await UserBuilder.add_user_info_to_conversation(
            patch_config, mock_message, conversation_info
        )

        assert result is not None
        assert result.user_id == "123"
        assert result.username == "Test User"
        assert result.is_bot is False  # Regular user, not our bot

        assert "123" in conversation_info.known_members
        assert conversation_info.known_members["123"] is result

    @pytest.mark.asyncio
    async def test_add_user_info_to_conversation_bot(self,
                                                     patch_config,
                                                     mock_bot_message,
                                                     conversation_info):
        """Test adding a bot user from a message"""
        result = await UserBuilder.add_user_info_to_conversation(
            patch_config, mock_bot_message, conversation_info
        )

        assert result is not None
        assert result.user_id == "12345"
        assert result.username == "Bot User"
        assert result.is_bot is True  # Should be marked as a bot

        assert "12345" in conversation_info.known_members
        assert conversation_info.known_members["12345"] is result

    @pytest.mark.asyncio
    async def test_add_user_info_to_conversation_existing(self,
                                                          patch_config,
                                                          mock_message,
                                                          conversation_info):
        """Test adding a user that already exists"""
        existing_user = UserInfo(
            user_id="123",
            username="Existing Name",  # Different from message
            is_bot=True  # Different from message
        )
        conversation_info.known_members["123"] = existing_user

        result = await UserBuilder.add_user_info_to_conversation(
            patch_config, mock_message, conversation_info
        )

        assert result is existing_user
        assert result.username == "Existing Name"  # Not updated
        assert result.is_bot is True  # Not updated

    @pytest.mark.asyncio
    async def test_add_user_info_to_conversation_invalid_message(self,
                                                                 patch_config,
                                                                 conversation_info):
        """Test adding a user from an invalid message"""
        assert await UserBuilder.add_user_info_to_conversation(
            patch_config, None, conversation_info
        ) is None

        # Test with message with no author
        message = MagicMock()
        delattr(message, 'author')
        assert await UserBuilder.add_user_info_to_conversation(
            patch_config, message, conversation_info
        ) is None

        # Test with message with None author
        message = MagicMock()
        message.author = None
        assert await UserBuilder.add_user_info_to_conversation(
            patch_config, message, conversation_info
        ) is None
