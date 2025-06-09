import pytest
from unittest.mock import MagicMock
from datetime import datetime

from src.adapters.telegram_adapter.conversation.data_classes import ConversationInfo
from src.adapters.telegram_adapter.conversation.message_builder import MessageBuilder
from src.core.conversation.base_data_classes import UserInfo, ThreadInfo

class TestMessageBuilder:
    """Tests for the MessageBuilder class"""

    @pytest.fixture
    def builder(self, telegram_config):
        """Create a fresh MessageBuilder for each test"""
        return MessageBuilder(telegram_config)

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
    def mock_conversation_info(self):
        """Create a mock conversation info"""
        return ConversationInfo(
            conversation_id="conversation123",
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

    def test_with_basic_info(self, builder, mock_message, mock_conversation_info):
        """Test adding basic message info"""
        result = builder.with_basic_info(mock_message, mock_conversation_info)

        assert builder.message_data["message_id"] == "123"
        assert builder.message_data["conversation_id"] == "conversation123"
        assert builder.message_data["timestamp"] == int(mock_message.date.timestamp())
        assert builder.message_data["is_direct_message"] is True
        assert result is builder

    def test_with_sender_info(self, builder, mock_user_info):
        """Test adding sender information"""
        result = builder.with_sender_info(mock_user_info)

        assert builder.message_data["sender_id"] == 789
        assert builder.message_data["sender_name"] == "Test User"
        assert builder.message_data["is_from_bot"] is False
        assert result is builder

    def test_with_sender_info_none(self, builder):
        """Test adding sender information when sender is None"""
        result = builder.with_sender_info(None)

        assert builder.message_data["is_from_bot"] is True
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
        result = builder.with_content(mock_message)

        assert builder.message_data["text"] == "Test message content"
        assert result is builder

    def test_with_content_no_message(self, builder):
        """Test adding content when message has no message attribute"""
        message = MagicMock()
        message.id = 123
        message = None

        result = builder.with_content(message)
        assert builder.message_data["text"] == ""
        assert result is builder

    def test_build(self, builder):
        """Test building the final message object"""
        builder.message_data = {
            "message_id": "123",
            "conversation_id": "conversation123",
            "text": "Test message"
        }

        result = builder.build()

        assert result is not builder.message_data
        assert result["message_id"] == "123"
        assert result["conversation_id"] == "conversation123"
        assert result["text"] == "Test message"

    def test_full_build_chain(self,
                              builder,
                              mock_message,
                              mock_user_info,
                              mock_thread_info,
                              mock_conversation_info):
        """Test a complete builder chain"""
        result = builder.reset() \
            .with_basic_info(mock_message, mock_conversation_info) \
            .with_sender_info(mock_user_info) \
            .with_thread_info(mock_thread_info) \
            .with_content(mock_message) \
            .build()

        assert result["message_id"] == "123"
        assert result["conversation_id"] == "conversation123"
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
