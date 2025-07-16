import pytest

from unittest.mock import patch
from src.adapters.zulip_adapter.conversation.data_classes import ConversationInfo
from src.adapters.zulip_adapter.conversation.message_builder import MessageBuilder
from src.core.cache.cache import Cache
from src.core.cache.user_cache import UserInfo

class TestMessageBuilder:
    """Tests for the MessageBuilder class with Zulip messages"""

    @pytest.fixture
    def builder(self):
        """Create a fresh MessageBuilder for each test"""
        return MessageBuilder()

    @pytest.fixture
    def mock_zulip_message(self):
        """Create a mock Zulip message"""
        return {
            "id": 123,
            "content": "Test message content",
            "timestamp": 1609502400,  # 2021-01-01 12:00:00 UTC
            "subject": "Test Topic",
            "type": "private"
        }

    @pytest.fixture
    def mock_zulip_stream_message(self):
        """Create a mock Zulip stream message"""
        return {
            "id": 456,
            "content": "Stream message content",
            "timestamp": 1609502400,
            "subject": "Test Topic",
            "type": "stream",
            "stream_id": 789,
            "display_recipient": "general"
        }

    @pytest.fixture
    def mock_sender(self):
        """Create a mock sender info"""
        return UserInfo(
            user_id="789",
            username="Test User",
            is_bot=False
        )

    @pytest.fixture
    def standard_private_conversation_id(self):
        """Create a standard conversation ID"""
        return "zulip_wWrMhAlqbPvWgzzVrBvL"

    @pytest.fixture
    def mock_private_conversation(self, standard_private_conversation_id):
        """Create a mock private conversation info"""
        return ConversationInfo(
            platform_conversation_id="123_456",
            conversation_id=standard_private_conversation_id,
            conversation_type="private"
        )

    @pytest.fixture
    def standard_stream_conversation_id(self):
        """Create a standard conversation ID"""
        return "zulip_dU5Ymp6wnpTzuHsCmFxV"

    @pytest.fixture
    def mock_stream_conversation(self, standard_stream_conversation_id):
        """Create a mock stream conversation info"""
        return ConversationInfo(
            platform_conversation_id="789/Test Topic",
            conversation_id=standard_stream_conversation_id,
            conversation_type="stream"
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

    def test_with_basic_info_private_message(self,
                                             builder,
                                             mock_zulip_message,
                                             mock_private_conversation,
                                             standard_private_conversation_id):
        """Test adding basic info from a private message"""
        result = builder.with_basic_info(mock_zulip_message, mock_private_conversation)

        assert builder.message_data["message_id"] == "123"
        assert builder.message_data["conversation_id"] == standard_private_conversation_id
        assert builder.message_data["timestamp"] == 1609502400
        assert builder.message_data["edit_timestamp"] is None
        assert builder.message_data["edited"] is False
        assert result is builder

    def test_with_basic_info_stream_message(self,
                                            builder,
                                            mock_zulip_stream_message,
                                            mock_stream_conversation,
                                            standard_stream_conversation_id):
        """Test adding basic info from a stream message"""
        result = builder.with_basic_info(mock_zulip_stream_message, mock_stream_conversation)

        assert builder.message_data["message_id"] == "456"
        assert builder.message_data["conversation_id"] == standard_stream_conversation_id
        assert builder.message_data["timestamp"] == 1609502400
        assert builder.message_data["edit_timestamp"] is None
        assert builder.message_data["edited"] is False
        assert result is builder

    def test_with_sender_id(self, cache_mock, builder, mock_sender):
        """Test adding sender information"""
        with patch.object(cache_mock.user_cache, "get_user_by_id", return_value=mock_sender):
            with patch.object(Cache, "get_instance", return_value=cache_mock):
                result = builder.with_sender_id(mock_sender.user_id)

                assert builder.message_data["sender_id"] == "789"
                assert builder.message_data["sender_name"] == "Test User"
                assert builder.message_data["is_from_bot"] is False
                assert result is builder

    def test_with_content(self, builder, mock_zulip_message):
        """Test adding message content"""
        result = builder.with_content({"message": mock_zulip_message})

        assert builder.message_data["text"] == "Test message content"
        assert result is builder

    def test_with_content_no_content(self, builder):
        """Test adding content when message has no content"""
        message = {"id": 123}  # No content field
        result = builder.with_content({"message": message})
        assert builder.message_data["text"] is None
        assert result is builder

    def test_build(self, builder, standard_private_conversation_id):
        """Test building the final message object"""
        builder.message_data = {
            "message_id": "123",
            "conversation_id": standard_private_conversation_id,
            "text": "Test message"
        }

        result = builder.build()

        assert result is not builder.message_data  # Check it's a copy
        assert result["message_id"] == "123"
        assert result["conversation_id"] == standard_private_conversation_id
        assert result["text"] == "Test message"

    def test_full_build_chain_private(self,
                                      cache_mock,
                                      builder,
                                      mock_zulip_message,
                                      mock_sender,
                                      mock_private_conversation,
                                      standard_private_conversation_id):
        """Test a complete builder chain for a private message"""
        with patch.object(cache_mock.user_cache, "get_user_by_id", return_value=mock_sender):
            with patch.object(Cache, "get_instance", return_value=cache_mock):
                result = builder.reset() \
                    .with_basic_info(mock_zulip_message, mock_private_conversation) \
                    .with_sender_id(mock_sender.user_id) \
                    .with_content({"message": mock_zulip_message}) \
                    .build()

                assert result["message_id"] == "123"
                assert result["conversation_id"] == standard_private_conversation_id
                assert result["timestamp"] == 1609502400
                assert result["sender_id"] == "789"
                assert result["sender_name"] == "Test User"
                assert result["is_from_bot"] is False
                assert result["text"] == "Test message content"

    def test_full_build_chain_stream(self,
                                      cache_mock,
                                      builder,
                                      mock_zulip_stream_message,
                                      mock_sender,
                                      mock_stream_conversation,
                                      standard_stream_conversation_id):
        """Test a complete builder chain for a stream message"""
        with patch.object(cache_mock.user_cache, "get_user_by_id", return_value=mock_sender):
            with patch.object(Cache, "get_instance", return_value=cache_mock):
                result = builder.reset() \
                    .with_basic_info(mock_zulip_stream_message, mock_stream_conversation) \
                    .with_sender_id(mock_sender.user_id) \
                    .with_content({"message": mock_zulip_stream_message}) \
                    .build()

                assert result["message_id"] == "456"
                assert result["conversation_id"] == standard_stream_conversation_id
                assert result["timestamp"] == 1609502400
                assert result["sender_id"] == "789"
                assert result["sender_name"] == "Test User"
                assert result["is_from_bot"] is False
                assert result["text"] == "Stream message content"
