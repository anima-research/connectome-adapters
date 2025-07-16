import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from src.adapters.slack_adapter.conversation.data_classes import ConversationInfo
from src.adapters.slack_adapter.conversation.message_builder import MessageBuilder
from src.core.cache.cache import Cache
from src.core.cache.user_cache import UserInfo
from src.core.conversation.base_data_classes import ThreadInfo

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
    def standard_conversation_id(self):
        """Create a mock standard conversation ID"""
        return "slack_inAx443FI3ABetPge"

    @pytest.fixture
    def mock_conversation_info(self, standard_conversation_id):
        """Create a mock conversation info"""
        return ConversationInfo(
            platform_conversation_id="T123/I456",
            conversation_id=standard_conversation_id,
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

    def test_with_basic_info(self,
                             builder,
                             mock_slack_message,
                             mock_conversation_info,
                             standard_conversation_id):
        """Test adding basic info from a Slack message"""
        result = builder.with_basic_info(mock_slack_message, mock_conversation_info)

        assert builder.message_data["message_id"] == "1609502400.123456"
        assert builder.message_data["conversation_id"] == standard_conversation_id
        assert builder.message_data["timestamp"] == 1609502400  # Converted to seconds
        assert builder.message_data["is_direct_message"] is True
        assert result is builder

    def test_with_sender_id(self, cache_mock, builder, mock_sender):
        """Test adding sender information"""
        with patch.object(cache_mock.user_cache, "get_user_by_id", return_value=mock_sender):
            with patch.object(Cache, "get_instance", return_value=cache_mock):
                result = builder.with_sender_id("U12345678")

                assert builder.message_data["sender_id"] == "U12345678"
                assert builder.message_data["sender_name"] == "Slack User"
                assert builder.message_data["is_from_bot"] is False
                assert result is builder

    def test_with_sender_id_none(self, cache_mock, builder):
        """Test adding None as sender information"""
        with patch.object(cache_mock.user_cache, "get_user_by_id", return_value=None):
            with patch.object(Cache, "get_instance", return_value=cache_mock):
                result = builder.with_sender_id(None)

                assert "sender_id" not in builder.message_data
                assert "sender_name" not in builder.message_data
                assert "is_from_bot" not in builder.message_data
                assert result is builder

    def test_with_content(self, builder, mock_slack_message):
        """Test adding message content"""
        result = builder.with_content({"message": mock_slack_message})

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

    def test_build(self, builder, standard_conversation_id):
        """Test building the final message object"""
        builder.message_data = {
            "message_id": "1609502400.123456",
            "conversation_id": standard_conversation_id,
            "text": "Test Slack message"
        }

        result = builder.build()

        assert result is not builder.message_data  # Check it's a copy
        assert result["message_id"] == "1609502400.123456"
        assert result["conversation_id"] == standard_conversation_id
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
                              cache_mock,
                              builder,
                              mock_slack_message,
                              mock_sender,
                              mock_thread_info,
                              mock_conversation_info,
                              standard_conversation_id):
        """Test a complete builder chain"""
        with patch.object(cache_mock.user_cache, "get_user_by_id", return_value=mock_sender):
            with patch.object(Cache, "get_instance", return_value=cache_mock):
                result = builder.reset() \
                    .with_basic_info(mock_slack_message, mock_conversation_info) \
                    .with_sender_id(mock_sender.user_id) \
                    .with_content({"message": mock_slack_message}) \
                    .with_thread_info(mock_thread_info) \
                    .build()

                assert result["message_id"] == "1609502400.123456"
                assert result["conversation_id"] == standard_conversation_id
                assert result["timestamp"] == 1609502400
                assert result["sender_id"] == "U12345678"
                assert result["sender_name"] == "Slack User"
                assert result["is_from_bot"] is False
                assert result["text"] == "Test message content"
                assert result["thread_id"] == "1609502400.123456"
                assert result["reply_to_message_id"] == "1609502400.123456"
                assert result["is_direct_message"] is True
