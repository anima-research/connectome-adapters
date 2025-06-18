import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone

from src.adapters.discord_adapter.conversation.data_classes import ConversationInfo
from src.adapters.discord_adapter.conversation.message_builder import MessageBuilder
from src.core.conversation.base_data_classes import UserInfo, ThreadInfo

class TestMessageBuilder:
    """Tests for the MessageBuilder class with Discord messages"""

    @pytest.fixture
    def builder(self):
        """Create a fresh MessageBuilder for each test"""
        return MessageBuilder()

    @pytest.fixture
    def mock_discord_message(self):
        """Create a mock Discord message"""
        message = MagicMock()
        message.id = 123
        message.content = "Test message content"
        message.created_at = datetime(2021, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        message.edited_at = None
        return message

    @pytest.fixture
    def mock_sender(self):
        """Create a mock sender info"""
        return UserInfo(
            user_id="789123456",
            username="Discord User",
            is_bot=False
        )

    @pytest.fixture
    def mock_thread_info(self):
        """Create a mock thread info"""
        return ThreadInfo(
            thread_id="456",
            root_message_id="456",
            messages=set(["123"]),
            last_activity=datetime.now()
        )

    @pytest.fixture
    def mock_conversation_info(self):
        """Create a mock conversation info"""
        return ConversationInfo(
            conversation_id="123456789",
            conversation_type="dm"
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
        assert builder.reset() is builder  # Should return self for chaining

    def test_with_basic_info(self, builder, mock_discord_message, mock_conversation_info):
        """Test adding basic info from a Discord message"""
        result = builder.with_basic_info(mock_discord_message, mock_conversation_info)

        assert builder.message_data["message_id"] == "123"
        assert builder.message_data["conversation_id"] == "123456789"
        assert builder.message_data["timestamp"] == 1609502400  # 2021-01-01 12:00:00 UTC in seconds
        assert builder.message_data["is_direct_message"] is True
        assert builder.message_data["edit_timestamp"] is None
        assert builder.message_data["edited"] is False
        assert result is builder

    def test_with_sender_info(self, builder, mock_sender):
        """Test adding sender information"""
        result = builder.with_sender_info(mock_sender)

        assert builder.message_data["sender_id"] == "789123456"
        assert builder.message_data["sender_name"] == "Discord User"
        assert builder.message_data["is_from_bot"] is False
        assert result is builder

    def test_with_sender_info_none(self, builder):
        """Test adding None as sender information"""
        result = builder.with_sender_info(None)

        # No sender keys should be added
        assert "sender_id" not in builder.message_data
        assert "sender_name" not in builder.message_data
        assert "is_from_bot" not in builder.message_data
        assert result is builder

    def test_with_content(self, builder, mock_discord_message):
        """Test adding message content"""
        result = builder.with_content(mock_discord_message)

        assert builder.message_data["text"] == "Test message content"
        assert result is builder

    def test_with_thread_info(self, builder, mock_thread_info):
        """Test adding thread information"""
        result = builder.with_thread_info(mock_thread_info)

        assert builder.message_data["thread_id"] == "456"
        assert builder.message_data["reply_to_message_id"] == "456"
        assert result is builder

    def test_with_thread_info_none(self, builder):
        """Test adding None as thread information"""
        result = builder.with_thread_info(None)

        # No thread keys should be added
        assert "thread_id" not in builder.message_data
        assert "reply_to_message_id" not in builder.message_data
        assert result is builder

    def test_build(self, builder):
        """Test building the final message object"""
        builder.message_data = {
            "message_id": "123456789",
            "conversation_id": "987654321",
            "text": "Test Discord message"
        }

        result = builder.build()

        assert result is not builder.message_data  # Check it's a copy
        assert result["message_id"] == "123456789"
        assert result["conversation_id"] == "987654321"
        assert result["text"] == "Test Discord message"

    def test_full_build_chain(self,
                              builder,
                              mock_discord_message,
                              mock_sender,
                              mock_thread_info,
                              mock_conversation_info):
        """Test a complete builder chain"""
        result = builder.reset() \
            .with_basic_info(mock_discord_message, mock_conversation_info) \
            .with_sender_info(mock_sender) \
            .with_content(mock_discord_message) \
            .with_thread_info(mock_thread_info) \
            .build()

        assert result["message_id"] == "123"
        assert result["conversation_id"] == "123456789"
        assert result["timestamp"] == 1609502400
        assert result["sender_id"] == "789123456"
        assert result["sender_name"] == "Discord User"
        assert result["is_from_bot"] is False
        assert result["text"] == "Test message content"
        assert result["thread_id"] == "456"
        assert result["reply_to_message_id"] == "456"
        assert result["edit_timestamp"] is None
        assert result["edited"] is False
