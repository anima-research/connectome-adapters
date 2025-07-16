import asyncio
import pytest

from datetime import datetime
from unittest.mock import AsyncMock

from src.adapters.slack_adapter.conversation.thread_handler import ThreadHandler
from src.adapters.slack_adapter.conversation.data_classes import ConversationInfo
from src.core.cache.message_cache import CachedMessage
from src.core.conversation.base_data_classes import ThreadInfo

class TestThreadHandler:
    """Tests for the Slack ThreadHandler class"""

    @pytest.fixture
    def conversation_info(self):
        """Create a ConversationInfo instance for testing"""
        return ConversationInfo(
            platform_conversation_id="T123/C456",
            conversation_id="slack_F0OIohoDYwVnEyYccO7j",
            conversation_type="channel"
        )

    @pytest.fixture
    def thread_info(self):
        """Create a ThreadInfo instance for testing"""
        return ThreadInfo(
            thread_id="1609502400.123456",
            title=None,
            root_message_id="1609502400.123456",
            messages=set(["1609502600.789012"]),
            last_activity=datetime.now()
        )

    @pytest.fixture
    def cached_message(self):
        """Create a CachedMessage instance for testing"""
        return CachedMessage(
            message_id="1609502600.789012",
            conversation_id="slack_F0OIohoDYwVnEyYccO7j",
            thread_id=None,
            sender_id="U12345678",
            sender_name="Slack User",
            text="Hello world",
            timestamp=int(datetime.now().timestamp()),
            edit_timestamp=None,
            edited=False,
            is_from_bot=False,
            reply_to_message_id=None
        )

    @pytest.fixture
    def thread_handler(self, cache_mock):
        """Create a ThreadHandler instance for testing"""
        thread_handler = ThreadHandler()
        thread_handler.cache = cache_mock
        return thread_handler

    @pytest.fixture
    def slack_message_in_thread(self):
        """Create a mock Slack message that's part of a thread"""
        return {
            "ts": "1609502600.789022",
            "thread_ts": "1609502400.123456",
            "text": "Hello, this is a reply",
            "user": "U12345678",
            "team": "T123",
            "channel": "C456",
            "type": "message"
        }

    @pytest.fixture
    def slack_message_not_in_thread(self):
        """Create a mock Slack message that's not part of a thread"""
        return {
            "ts": "1609502600.789032",
            "text": "Hello, this is not a reply",
            "user": "U12345678",
            "team": "T123",
            "channel": "C456",
            "type": "message"
        }

    class TestExtractReplyToId:
        """Tests for _extract_reply_to_id method"""

        def test_with_thread_ts(self, thread_handler, slack_message_in_thread):
            """Test extracting reply ID from message with thread_ts"""
            assert thread_handler._extract_reply_to_id(slack_message_in_thread) == "1609502400.123456"

        def test_without_thread_ts(self, thread_handler, slack_message_not_in_thread):
            """Test extracting reply ID from message without thread_ts"""
            assert thread_handler._extract_reply_to_id(slack_message_not_in_thread) == ""

        def test_null_message(self, thread_handler):
            """Test extracting reply ID from null message"""
            assert thread_handler._extract_reply_to_id(None) is None

    class TestAddThreadInfo:
        """Tests for add_thread_info method"""

        @pytest.mark.asyncio
        async def test_new_thread(self,
                                  thread_handler,
                                  conversation_info,
                                  slack_message_in_thread):
            """Test creating a new thread"""
            result = await thread_handler.add_thread_info(
                slack_message_in_thread, conversation_info
            )

            assert result is not None
            assert result.thread_id == "1609502400.123456"
            assert result.root_message_id == "1609502400.123456"
            assert len(result.messages) == 1
            assert "1609502600.789022" in result.messages
            assert result.last_activity is not None

            assert "1609502400.123456" in conversation_info.threads
            assert conversation_info.threads["1609502400.123456"] == result

        @pytest.mark.asyncio
        async def test_existing_thread(self,
                                       thread_handler,
                                       conversation_info,
                                       thread_info,
                                       slack_message_in_thread):
            """Test adding to an existing thread"""
            conversation_info.threads["1609502400.123456"] = thread_info
            original_message_count = len(thread_info.messages)
            original_last_activity = thread_info.last_activity

            await asyncio.sleep(0.01)  # Ensure time difference in last_activity

            result = await thread_handler.add_thread_info(
                slack_message_in_thread, conversation_info
            )

            assert result is not None
            assert result.thread_id == "1609502400.123456"
            assert len(result.messages) == original_message_count + 1
            assert "1609502600.789022" in result.messages
            assert result.last_activity > original_last_activity

            assert "1609502400.123456" in conversation_info.threads
            assert conversation_info.threads["1609502400.123456"] == result

    class TestRemoveThreadInfo:
        """Tests for remove_thread_info method"""

        def test_remove_from_thread(self,
                                    thread_handler,
                                    conversation_info,
                                    cached_message,
                                    thread_info):
            """Test removing a message from a thread that has multiple messages"""
            thread_info.messages.add("1609502700.987654")
            conversation_info.threads["1609502400.123456"] = thread_info
            cached_message.thread_id = "1609502400.123456"

            thread_handler.remove_thread_info(conversation_info, cached_message)

            assert "1609502400.123456" in conversation_info.threads
            assert len(conversation_info.threads["1609502400.123456"].messages) == 1
            assert "1609502600.789012" not in conversation_info.threads["1609502400.123456"].messages
            assert "1609502700.987654" in conversation_info.threads["1609502400.123456"].messages

        def test_remove_last_message_from_thread(self,
                                                 thread_handler,
                                                 conversation_info,
                                                 cached_message,
                                                 thread_info):
            """Test removing the last message from a thread"""
            conversation_info.threads["1609502400.123456"] = thread_info
            cached_message.thread_id = "1609502400.123456"

            thread_handler.remove_thread_info(conversation_info, cached_message)

            assert "1609502400.123456" not in conversation_info.threads

