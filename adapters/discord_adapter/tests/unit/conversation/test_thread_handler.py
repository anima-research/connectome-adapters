import asyncio
import pytest

from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from adapters.discord_adapter.adapter.conversation.thread_handler import ThreadHandler
from adapters.discord_adapter.adapter.conversation.data_classes import ConversationInfo
from core.cache.message_cache import CachedMessage
from core.conversation.base_data_classes import ThreadInfo

class TestThreadHandler:
    """Tests for the Discord ThreadHandler class"""

    @pytest.fixture
    def message_cache_mock(self):
        """Create a mocked MessageCache"""
        return AsyncMock()

    @pytest.fixture
    def conversation_info(self):
        """Create a ConversationInfo instance for testing"""
        return ConversationInfo(
            conversation_id="123456789",
            conversation_type="text_channel"
        )

    @pytest.fixture
    def thread_info(self):
        """Create a ThreadInfo instance for testing"""
        return ThreadInfo(
            thread_id="789",
            title=None,
            root_message_id="789",
            messages=set(["some_other_message_id"]),
            last_activity=datetime.now()
        )

    @pytest.fixture
    def cached_message(self):
        """Create a CachedMessage instance for testing"""
        return CachedMessage(
            message_id="123",
            conversation_id="123456789",
            thread_id=None,
            sender_id="456789123",
            sender_name="Discord User",
            text="Hello world",
            timestamp=int(datetime.now().timestamp() * 1000),
            is_from_bot=False,
            reply_to_message_id=None
        )

    @pytest.fixture
    def thread_handler(self, message_cache_mock):
        """Create a ThreadHandler instance for testing"""
        return ThreadHandler(message_cache_mock)

    @pytest.fixture
    def mock_reference(self):
        """Create a mock Discord message reference"""
        reference = MagicMock()
        reference.message_id = 456789
        return reference

    @pytest.fixture
    def discord_message(self, mock_reference):
        """Create a mock Discord message with a reference"""
        message = MagicMock()
        message.id = 123456
        message.reference = mock_reference
        message.content = "Hello, this is a reply"
        return message

    @pytest.fixture
    def discord_message_no_reference(self):
        """Create a mock Discord message without a reference"""
        message = MagicMock()
        message.id = 123456
        message.reference = None
        message.content = "Hello, this is not a reply"
        return message

    class TestExtractReplyToId:
        """Tests for _extract_reply_to_id method"""

        def test_with_reference(self, thread_handler, discord_message):
            """Test extracting reply ID from message with reference"""
            assert thread_handler._extract_reply_to_id(discord_message) == "456789"

        def test_without_reference(self, thread_handler, discord_message_no_reference):
            """Test extracting reply ID from message without reference"""
            assert thread_handler._extract_reply_to_id(discord_message_no_reference) is None

        def test_null_message(self, thread_handler):
            """Test extracting reply ID from null message"""
            assert thread_handler._extract_reply_to_id(None) is None

        def test_message_without_reference_attribute(self, thread_handler):
            """Test extracting reply ID from message without reference attribute"""
            message = MagicMock()
            delattr(message, 'reference')

            assert thread_handler._extract_reply_to_id(message) is None

    class TestAddThreadInfo:
        """Tests for add_thread_info method"""

        @pytest.mark.asyncio
        async def test_no_reference(self,
                                    thread_handler,
                                    conversation_info,
                                    discord_message_no_reference):
            """Test handling message with no reference"""
            assert await thread_handler.add_thread_info(
                discord_message_no_reference, conversation_info
            ) is None
            assert len(conversation_info.threads) == 0

        @pytest.mark.asyncio
        async def test_new_thread(self,
                                  thread_handler,
                                  conversation_info,
                                  discord_message):
            """Test creating a new thread"""
            result = await thread_handler.add_thread_info(
                discord_message, conversation_info
            )

            assert result is not None
            assert result.thread_id == "456789"
            assert result.root_message_id == "456789"
            assert len(result.messages) == 1
            assert result.last_activity is not None

            assert "456789" in conversation_info.threads
            assert conversation_info.threads["456789"] == result

        @pytest.mark.asyncio
        async def test_existing_thread(self,
                                       thread_handler,
                                       conversation_info,
                                       thread_info,
                                       discord_message):
            """Test adding to an existing thread"""
            discord_message.reference.message_id = 789
            conversation_info.threads["789"] = thread_info
            original_message_count = len(thread_info.messages)
            original_last_activity = thread_info.last_activity

            await asyncio.sleep(0.01)

            result = await thread_handler.add_thread_info(
                discord_message, conversation_info
            )

            assert result is not None
            assert result.thread_id == "789"
            assert len(result.messages) == original_message_count + 1
            assert result.last_activity > original_last_activity

            assert "789" in conversation_info.threads
            assert conversation_info.threads["789"] == result

        @pytest.mark.asyncio
        async def test_reply_to_reply(self,
                                      thread_handler,
                                      conversation_info,
                                      discord_message,
                                      cached_message):
            """Test handling reply to a message that is itself a reply"""
            original_thread = ThreadInfo(
                thread_id="123",
                root_message_id="123",
                messages=set(["456788", "456789"])
            )
            conversation_info.threads["123"] = original_thread

            # Setup a replied message that itself is a reply
            replied_message = CachedMessage(
                message_id="456789",  # This matches our discord_message's reference
                conversation_id=cached_message.conversation_id,
                thread_id="123",  # This message is part of thread 123
                sender_id=cached_message.sender_id,
                sender_name=cached_message.sender_name,
                text="I am replying to message 123",
                timestamp=cached_message.timestamp,
                is_from_bot=cached_message.is_from_bot,
                reply_to_message_id="123"  # This message replies to message 123
            )
            thread_handler.message_cache.get_message_by_id.return_value = replied_message

            result = await thread_handler.add_thread_info(
                discord_message, conversation_info
            )

            assert result is not None
            assert result.thread_id == "456789"  # Thread ID is the immediate reply target
            assert result.root_message_id == "123"  # But root ID is from the original thread
            assert len(result.messages) == 1

            assert "456789" in conversation_info.threads
            assert conversation_info.threads["456789"] == result

            thread_handler.message_cache.get_message_by_id.assert_called_with(
                conversation_id=conversation_info.conversation_id,
                message_id="456789"
            )

    class TestRemoveThreadInfo:
        """Tests for remove_thread_info method"""

        def test_remove_from_thread(self,
                                    thread_handler,
                                    conversation_info,
                                    cached_message):
            """Test removing a message from a thread that has multiple messages"""
            test_thread = ThreadInfo(
                thread_id="test_thread",
                root_message_id="123",
                messages=set(["123", "124"])
            )
            conversation_info.threads["test_thread"] = test_thread
            cached_message.thread_id = "test_thread"

            thread_handler.remove_thread_info(conversation_info, cached_message)

            assert "test_thread" in conversation_info.threads
            assert len(conversation_info.threads["test_thread"].messages) == 1

        def test_remove_last_message_from_thread(self,
                                                 thread_handler,
                                                 conversation_info,
                                                 cached_message):
            """Test removing the last message from a thread"""
            test_thread = ThreadInfo(
                thread_id="test_thread",
                root_message_id="123",
                messages=set(["123"])
            )
            conversation_info.threads["test_thread"] = test_thread
            cached_message.thread_id = "test_thread"

            thread_handler.remove_thread_info(conversation_info, cached_message)

            assert "test_thread" not in conversation_info.threads
