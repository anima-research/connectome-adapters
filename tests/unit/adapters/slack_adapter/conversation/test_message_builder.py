import pytest
from datetime import datetime
from unittest.mock import MagicMock

from src.adapters.slack_adapter.conversation.data_classes import ConversationInfo
from src.adapters.slack_adapter.conversation.message_builder import MessageBuilder
from src.core.conversation.base_data_classes import UserInfo, ThreadInfo

class TestMessageBuilder:
    """Tests for the MessageBuilder class with Slack messages"""

    @pytest.fixture
    def builder(self):
        """Create a fresh MessageBuilder for each test"""
        return MessageBuilder()

    @pytest.fixture
    def mock_slack_message(self):
        """Create a mock Slack message"""
        return {
            "ts": "1609502400.123456",
            "text": "Test message content",
            "user": "U12345678",
            "team": "T87654321",
            "channel": "C11223344",
            "type": "message",
            "channel_type": "im",
            "blocks": [
                {
                    "type": "rich_text",
                    "block_id": "abc123",
                    "elements": [
                        {
                            "type": "rich_text_section",
                            "elements": [
                                {
                                    "type": "text",
                                    "text": "Test message content"
                                }
                            ]
                        }
                    ]
                }
            ]
        }

    @pytest.fixture
    def mock_slack_thread_message(self):
        """Create a mock Slack message in a thread"""
        return {
            "ts": "1609502500.654321",
            "thread_ts": "1609502400.123456",
            "text": "Test thread reply",
            "user": "U12345678",
            "team": "T87654321",
            "channel": "C11223344",
            "type": "message",
            "parent_user_id": "U12345678"
        }

    @pytest.fixture
    def mock_sender(self):
        """Create a mock sender info"""
        return UserInfo(
            user_id="U12345678",
            username="Slack User",
            is_bot=False
        )

    @pytest.fixture
    def mock_thread_info(self):
        """Create a mock thread info"""
        return ThreadInfo(
            thread_id="1609502400.123456",
            root_message_id="1609502400.123456",
            messages=set(["1609502500.654321"]),
            last_activity=datetime.now()
        )

    @pytest.fixture
    def mock_conversation_info(self):
        """Create a mock conversation info"""
        return ConversationInfo(
            conversation_id="T87654321/C11223344",
            conversation_type="im"
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

    def test_with_basic_info(self, builder, mock_slack_message, mock_conversation_info):
        """Test adding basic info from a Slack message"""
        result = builder.with_basic_info(mock_slack_message, mock_conversation_info)

        assert builder.message_data["message_id"] == "1609502400.123456"
        assert builder.message_data["conversation_id"] == "T87654321/C11223344"
        assert builder.message_data["timestamp"] == 1609502400  # Converted to seconds
        assert builder.message_data["is_direct_message"] is True
        assert result is builder

    def test_with_sender_info(self, builder, mock_sender):
        """Test adding sender information"""
        result = builder.with_sender_info(mock_sender)

        assert builder.message_data["sender_id"] == "U12345678"
        assert builder.message_data["sender_name"] == "Slack User"
        assert builder.message_data["is_from_bot"] is False
        assert result is builder

    def test_with_sender_info_none(self, builder):
        """Test adding None as sender information"""
        result = builder.with_sender_info(None)

        assert "sender_id" not in builder.message_data
        assert "sender_name" not in builder.message_data
        assert "is_from_bot" not in builder.message_data
        assert result is builder

    def test_with_content(self, builder, mock_slack_message):
        """Test adding message content"""
        result = builder.with_content(mock_slack_message)

        assert builder.message_data["text"] == "Test message content"
        assert result is builder

    def test_with_thread_info(self, builder, mock_thread_info):
        """Test adding thread information"""
        result = builder.with_thread_info(mock_thread_info)

        assert builder.message_data["thread_id"] == "1609502400.123456"
        assert builder.message_data["reply_to_message_id"] == "1609502400.123456"
        assert result is builder

    def test_with_thread_info_none(self, builder):
        """Test adding None as thread information"""
        result = builder.with_thread_info(None)

        assert "thread_id" not in builder.message_data
        assert "reply_to_message_id" not in builder.message_data
        assert result is builder

    def test_build(self, builder):
        """Test building the final message object"""
        builder.message_data = {
            "message_id": "1609502400.123456",
            "conversation_id": "T87654321/C11223344",
            "text": "Test Slack message"
        }

        result = builder.build()

        assert result is not builder.message_data  # Check it's a copy
        assert result["message_id"] == "1609502400.123456"
        assert result["conversation_id"] == "T87654321/C11223344"
        assert result["text"] == "Test Slack message"

    def test_slack_timestamp_conversion(self, builder, mock_conversation_info):
        """Test that Slack timestamps are properly converted to milliseconds"""
        message = {
            "ts": "1609502400.123456",  # Slack format: seconds.microseconds
            "text": "Test message"
        }

        builder.with_basic_info(message, mock_conversation_info)

        # Should be converted to seconds
        expected_ms = int(float("1609502400.123456"))
        assert builder.message_data["timestamp"] == expected_ms

    def test_full_build_chain(self,
                              builder,
                              mock_slack_message,
                              mock_sender,
                              mock_thread_info,
                              mock_conversation_info):
        """Test a complete builder chain"""
        result = builder.reset() \
            .with_basic_info(mock_slack_message, mock_conversation_info) \
            .with_sender_info(mock_sender) \
            .with_content(mock_slack_message) \
            .with_thread_info(mock_thread_info) \
            .build()

        assert result["message_id"] == "1609502400.123456"
        assert result["conversation_id"] == "T87654321/C11223344"
        assert result["timestamp"] == 1609502400
        assert result["sender_id"] == "U12345678"
        assert result["sender_name"] == "Slack User"
        assert result["is_from_bot"] is False
        assert result["text"] == "Test message content"
        assert result["thread_id"] == "1609502400.123456"
        assert result["reply_to_message_id"] == "1609502400.123456"
        assert result["is_direct_message"] is True
