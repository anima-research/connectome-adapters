import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from src.adapters.telegram_adapter.conversation.data_classes import ConversationInfo
from src.adapters.telegram_adapter.conversation.message_builder import MessageBuilder
from src.core.cache.cache import Cache
from src.core.cache.user_cache import UserInfo
from src.core.conversation.base_data_classes import ThreadInfo

class TestMessageBuilder:
    """Tests for the MessageBuilder class"""

    @pytest.fixture
    def builder(self):
        """Create a fresh MessageBuilder for each test"""
        return MessageBuilder()

    @pytest.fixture
    def mock_message(self):
        """Create a mock Telethon message"""
        message = MagicMock()
        message.id = 123
        message.message = "Test message content"
        message.date = datetime(2023, 1, 1, 12, 0, 0)
        reply_to = MagicMock()
        reply_to.reply_to_msg_id = 456
        message.reply_to = reply_to
        return message

    @pytest.fixture
    def mock_user_info(self):
        """Create a mock user info"""
        return UserInfo(
            user_id=789,
            first_name="Test",
            last_name="User",
            is_bot=False
        )

    @pytest.fixture
    def mock_thread_info(self):
        """Create a mock thread info"""
        return ThreadInfo(
            thread_id="122",
            title="Test Thread",
            root_message_id="122",
            last_activity=datetime(2023, 1, 1, 12, 0, 0)
        )

    @pytest.fixture
    def standard_conversation_id(self):
        """Setup a test conversation info"""
        return "telegram_gpuesUol8zJmOXetFBnj"

    @pytest.fixture
    def mock_conversation_info(self, standard_conversation_id):
        """Create a mock conversation info"""
        return ConversationInfo(
            platform_conversation_id="conversation123",
            conversation_id=standard_conversation_id,
            conversation_type="private"
        )

    def test_initialization(self, builder):
        """Test that the builder initializes with empty message data"""
        assert isinstance(builder.message_data, dict)
        assert len(builder.message_data) == 0

    def test_reset(self, builder):
        """Test that the reset method clears message data"""
        builder.message_data["test"] = "value"
        builder.reset()

        assert len(builder.message_data) == 0
        assert builder.reset() is builder

    def test_with_basic_info(self,
                             builder,
                             mock_message,
                             mock_conversation_info,
                             standard_conversation_id):
        """Test adding basic message info"""
        result = builder.with_basic_info(mock_message, mock_conversation_info)

        assert builder.message_data["message_id"] == "123"
        assert builder.message_data["conversation_id"] == standard_conversation_id
        assert builder.message_data["timestamp"] == int(mock_message.date.timestamp())
        assert builder.message_data["is_direct_message"] is True
        assert result is builder

    def test_with_sender_id(self, cache_mock, builder, mock_user_info):
        """Test adding sender information"""
        with patch.object(cache_mock.user_cache, "get_user_by_id", return_value=mock_user_info):
            with patch.object(Cache, "get_instance", return_value=cache_mock):
                result = builder.with_sender_id(mock_user_info.user_id)

                assert builder.message_data["sender_id"] == 789
                assert builder.message_data["sender_name"] == "Test User"
                assert builder.message_data["is_from_bot"] is False
                assert result is builder

    def test_with_thread_info(self, builder, mock_thread_info):
        """Test adding thread information"""
        result = builder.with_thread_info(mock_thread_info)

        assert builder.message_data["thread_id"] == "122"
        assert builder.message_data["reply_to_message_id"] == "122"
        assert result is builder

    def test_with_thread_info_no_thread(self, builder):
        """Test adding thread info when thread_id is None"""
        result = builder.with_thread_info(None)

        assert "thread_id" not in builder.message_data
        assert "reply_to_message_id" not in builder.message_data
        assert result is builder

    def test_with_content(self, builder, mock_message):
        """Test adding message content"""
        result = builder.with_content({"message": mock_message})

        assert builder.message_data["text"] == "Test message content"
        assert result is builder

    def test_with_content_no_message(self, builder):
        """Test adding content when message has no message attribute"""
        message = MagicMock()
        message.id = 123
        message = None

        result = builder.with_content({"message": message})
        assert builder.message_data["text"] == ""
        assert result is builder

    def test_build(self, builder, standard_conversation_id):
        """Test building the final message object"""
        builder.message_data = {
            "message_id": "123",
            "conversation_id": standard_conversation_id,
            "text": "Test message"
        }

        result = builder.build()

        assert result is not builder.message_data
        assert result["message_id"] == "123"
        assert result["conversation_id"] == standard_conversation_id
        assert result["text"] == "Test message"

    def test_full_build_chain(self,
                              cache_mock,
                              builder,
                              mock_message,
                              mock_user_info,
                              mock_thread_info,
                              mock_conversation_info,
                              standard_conversation_id):
        """Test a complete builder chain"""
        with patch.object(cache_mock.user_cache, "get_user_by_id", return_value=mock_user_info):
            with patch.object(Cache, "get_instance", return_value=cache_mock):
                result = builder.reset() \
                    .with_basic_info(mock_message, mock_conversation_info) \
                    .with_sender_id(mock_user_info.user_id) \
                    .with_thread_info(mock_thread_info) \
                    .with_content({"message": mock_message}) \
                    .build()

                assert result["message_id"] == "123"
                assert result["conversation_id"] == standard_conversation_id
                assert result["timestamp"] == int(mock_message.date.timestamp())
                assert result["sender_id"] == 789
                assert result["sender_name"] == "Test User"
                assert result["is_from_bot"] is False
                assert result["thread_id"] == "122"
                assert result["reply_to_message_id"] == "122"
                assert result["text"] == "Test message content"
                assert result["is_direct_message"] is True

    def test_build_independence(self, builder):
        """Test that subsequent builds don't affect each other"""
        # First build
        builder.message_data = {"key": "value1"}
        first_result = builder.build()

        # Modify data and build again
        builder.message_data["key"] = "value2"
        second_result = builder.build()

        # Check first result is unchanged
        assert first_result["key"] == "value1"
        assert second_result["key"] == "value2"

        # Modify the result and check it doesn"t affect the builder
        first_result["new_key"] = "new_value"
        assert "new_key" not in builder.message_data
