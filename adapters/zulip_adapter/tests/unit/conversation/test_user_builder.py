import pytest
from unittest.mock import MagicMock

from adapters.zulip_adapter.adapter.conversation.data_classes import ConversationInfo
from adapters.zulip_adapter.adapter.conversation.user_builder import UserBuilder

from core.conversation.base_data_classes import UserInfo
from core.utils.config import Config

class TestUserBuilder:
    """Tests for the UserBuilder class with Zulip message format"""

    @pytest.fixture
    def config_mock(self):
        """Create a mock Config object"""
        config = MagicMock(spec=Config)
        config.get_setting.side_effect = lambda section, key, default=None: {
            ("adapter", "adapter_id"): "999",
            ("adapter", "adapter_email"): "bot@example.com"
        }.get((section, key), default)
        return config

    @pytest.fixture
    def mock_stream_message(self):
        """Create a mock Zulip stream message"""
        return {
            "type": "stream",
            "sender_id": 123,
            "sender_full_name": "Test User",
            "sender_email": "user@example.com",
            "display_recipient": "General stream"  # Stream name
        }

    @pytest.fixture
    def mock_private_message(self):
        """Create a mock Zulip private message"""
        return {
            "type": "private",
            "sender_id": 123,
            "sender_full_name": "Test User",
            "sender_email": "user@example.com",
            "display_recipient": [
                {
                    "id": 123,
                    "full_name": "Test User",
                    "email": "user@example.com",
                    "is_mirror_dummy": False
                },
                {
                    "id": 456,
                    "full_name": "Another User",
                    "email": "another@example.com",
                    "is_mirror_dummy": False
                },
                {
                    "id": 999,
                    "full_name": "Bot User",
                    "email": "bot@example.com",
                    "is_mirror_dummy": False
                }
            ]
        }

    @pytest.fixture
    def conversation_info(self):
        """Create a conversation info object"""
        return ConversationInfo(
            conversation_id="123_456_999",
            conversation_type="private"
        )

    def test_from_adapter(self, config_mock):
        """Test the from_adapter method"""
        # Not the adapter
        assert UserBuilder.from_adapter(config_mock, "123", "user@example.com") is False

        # Is the adapter
        assert UserBuilder.from_adapter(config_mock, "999", "bot@example.com") is True

        # Partial match should fail
        assert UserBuilder.from_adapter(config_mock, "999", "wrong@example.com") is False
        assert UserBuilder.from_adapter(config_mock, "123", "bot@example.com") is False

    def test_add_known_members_to_private_conversation(self,
                                                       config_mock,
                                                       mock_private_message,
                                                       conversation_info):
        """Test adding recipients from a private message"""
        assert len(conversation_info.known_members) == 0

        UserBuilder.add_known_members_to_private_conversation(
            config_mock, mock_private_message, conversation_info
        )

        assert len(conversation_info.known_members) == 3

        user1 = conversation_info.known_members["123"]
        assert user1.user_id == "123"
        assert user1.username == "Test User"
        assert user1.email == "user@example.com"
        assert user1.is_bot is False

        user2 = conversation_info.known_members["456"]
        assert user2.user_id == "456"
        assert user2.username == "Another User"
        assert user2.email == "another@example.com"
        assert user2.is_bot is False

        bot_user = conversation_info.known_members["999"]
        assert bot_user.user_id == "999"
        assert bot_user.username == "Bot User"
        assert bot_user.email == "bot@example.com"
        assert bot_user.is_bot is True  # True because it matches adapter ID and email

        # Calling again should not add any more members
        conversation_info.known_members.clear()
        conversation_info.known_members["123"] = UserInfo(user_id="123")

        UserBuilder.add_known_members_to_private_conversation(
            config_mock, mock_private_message, conversation_info
        )

        assert len(conversation_info.known_members) == 1

    @pytest.mark.asyncio
    async def test_add_user_info_to_conversation_stream(self,
                                                        config_mock,
                                                        mock_stream_message,
                                                        conversation_info):
        """Test adding a user from a stream message"""
        result = await UserBuilder.add_user_info_to_conversation(
            config_mock, mock_stream_message, conversation_info
        )

        # Should return the added user
        assert result is not None
        assert result.user_id == "123"
        assert result.username == "Test User"
        assert result.email == "user@example.com"
        assert result.is_bot is False

        # Should have added to conversation_info
        assert "123" in conversation_info.known_members
        assert conversation_info.known_members["123"] is result

    @pytest.mark.asyncio
    async def test_add_user_info_to_conversation_private(self,
                                                         config_mock,
                                                         mock_private_message,
                                                         conversation_info):
        """Test adding a user from a private message"""
        # This should also add all recipients
        result = await UserBuilder.add_user_info_to_conversation(
            config_mock, mock_private_message, conversation_info
        )

        # Should return the sender's user info
        assert result is not None
        assert result.user_id == "123"

        # Should have added all recipients to conversation_info
        assert len(conversation_info.known_members) == 3
        assert "123" in conversation_info.known_members
        assert "456" in conversation_info.known_members
        assert "999" in conversation_info.known_members

    @pytest.mark.asyncio
    async def test_add_user_info_to_conversation_existing(self,
                                                          config_mock,
                                                          mock_stream_message,
                                                          conversation_info):
        """Test adding a user that already exists"""
        existing_user = UserInfo(
            user_id="123",
            username="Existing Name",  # Different from message
            email="existing@example.com",  # Different from message
            is_bot=True  # Different from message
        )
        conversation_info.known_members["123"] = existing_user

        result = await UserBuilder.add_user_info_to_conversation(
            config_mock, mock_stream_message, conversation_info
        )

        # Should return the existing user without modifying it
        assert result is existing_user
        assert result.username == "Existing Name"  # Not updated
        assert result.email == "existing@example.com"  # Not updated
        assert result.is_bot is True  # Not updated
