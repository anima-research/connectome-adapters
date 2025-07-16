import asyncio
import pytest

from unittest.mock import AsyncMock, patch
from datetime import datetime

from src.adapters.zulip_adapter.conversation.thread_handler import ThreadHandler
from src.adapters.zulip_adapter.conversation.data_classes import ConversationInfo
from src.core.cache.message_cache import CachedMessage
from src.core.conversation.base_data_classes import ThreadInfo

class TestThreadHandler:
    """Tests for the ThreadHandler class"""

    @pytest.fixture
    def standard_conversation_id(self):
        """Create a standard conversation ID"""
        return "zulip_wWrMhAlqbPvWgzzVrBvL"

    @pytest.fixture
    def conversation_info(self, standard_conversation_id):
        """Create a ConversationInfo instance for testing"""
        return ConversationInfo(
            platform_conversation_id="123_456",
            conversation_id=standard_conversation_id,
            conversation_type="private"
        )

    @pytest.fixture
    def thread_info(self):
        """Create a ThreadInfo instance for testing"""
        return ThreadInfo(
            thread_id="789",
            title=None,
            root_message_id="789",
            messages=set(["123"]),
            last_activity=datetime.now()
        )

    @pytest.fixture
    def cached_message(self, standard_conversation_id):
        """Create a CachedMessage instance for testing"""
        return CachedMessage(
            message_id="123",
            conversation_id=standard_conversation_id,
            thread_id=None,
            sender_id="user1",
            sender_name="User One",
            text="Hello world",
            timestamp=int(datetime.now().timestamp()),
            edit_timestamp=None,
            edited=False,
            is_from_bot=False,
            reply_to_message_id=None
        )

    @pytest.fixture
    def thread_handler(self):
        """Create a ThreadHandler instance for testing"""
        return ThreadHandler()

    class TestAddThreadInfoToConversation:
        """Tests for add_thread_info_to_conversation method"""

        @pytest.mark.asyncio
        async def test_no_content(self, thread_handler, conversation_info):
            """Test handling message with no content"""
            assert await thread_handler.add_thread_info({}, conversation_info) is None
            assert len(conversation_info.threads) == 0

        @pytest.mark.asyncio
        async def test_no_reply(self, thread_handler, conversation_info):
            """Test handling message with no reply"""
            result = await thread_handler.add_thread_info(
                {"content": "Just a regular message"}, conversation_info
            )

            assert result is None
            assert len(conversation_info.threads) == 0

        @pytest.mark.asyncio
        async def test_new_thread(self, thread_handler, conversation_info):
            """Test creating a new thread"""
            message = {
                "id": 789,
                "content": '@_**User|123** [said](https://zulip.at-hub.com/123-dm/near/456):\n```quote\nHello\n```\nHi there'
            }
            result = await thread_handler.add_thread_info(message, conversation_info)

            assert result is not None
            assert result.thread_id == "456"
            assert result.root_message_id == "456"
            assert len(result.messages) == 1
            assert result.last_activity is not None

            assert "456" in conversation_info.threads
            assert conversation_info.threads["456"] == result

        @pytest.mark.asyncio
        async def test_existing_thread(self, thread_handler, conversation_info, thread_info):
            """Test adding to an existing thread"""
            conversation_info.threads["789"] = thread_info
            original_message_count = len(thread_info.messages)
            original_last_activity = thread_info.last_activity

            message = {
                "id": 1000,
                "content": '@_**User|123** [said](https://zulip.at-hub.com/123-dm/near/789):\n```quote\nHello\n```\nHi there'
            }

            await asyncio.sleep(0.01)

            result = await thread_handler.add_thread_info(message, conversation_info)

            assert result is not None
            assert result.thread_id == "789"
            assert len(result.messages) == original_message_count + 1
            assert result.last_activity > original_last_activity

            assert "789" in conversation_info.threads
            assert conversation_info.threads["789"] == result

        @pytest.mark.asyncio
        async def test_reply_to_reply(self, thread_handler, conversation_info, cached_message):
            """Test handling reply to a message that is itself a reply"""
            conversation_info.threads["123"] = ThreadInfo(
                thread_id="123",
                root_message_id="123",
                messages=set(["456"])
            )
            replied_message = CachedMessage(
                message_id="456",
                conversation_id=cached_message.conversation_id,
                thread_id="123",
                sender_id=cached_message.sender_id,
                sender_name=cached_message.sender_name,
                text=cached_message.text,
                timestamp=cached_message.timestamp,
                edit_timestamp=cached_message.edit_timestamp,
                edited=cached_message.edited,
                is_from_bot=cached_message.is_from_bot,
                reply_to_message_id="123"  # This message replies to message 123
            )

            with patch.object(thread_handler.cache.message_cache, "get_message_by_id", return_value=replied_message):
                message = {
                    "id": 789,
                    "content": '@_**User|123** [said](https://zulip.at-hub.com/123-dm/near/456):\n```quote\nHello\n```\nHi there'
                }
                result = await thread_handler.add_thread_info(message, conversation_info)

                assert result is not None
                assert result.thread_id == "456"  # Thread ID is the immediate reply target
                assert result.root_message_id == "123"  # But root ID is from the original thread
                assert len(result.messages) == 1

                assert "456" in conversation_info.threads
                assert conversation_info.threads["456"] == result

    class TestUpdateThreadInfo:
        """Tests for update_thread_info method"""

        @pytest.mark.asyncio
        async def test_no_change(self, thread_handler, conversation_info):
            """Test when threading hasn't changed"""
            message = {
                "message_id": "123",
                "orig_content": '@_**User|123** [said](https://zulip.at-hub.com/123-dm/near/456):\n```quote\nHello\n```\nOriginal reply',
                "content": '@_**User|123** [said](https://zulip.at-hub.com/123-dm/near/456):\n```quote\nHello\n```\nEdited reply'
            }
            changed, thread_info = await thread_handler.update_thread_info(
                message, conversation_info
            )

            assert changed is False
            assert thread_info is None

        @pytest.mark.asyncio
        async def test_reply_removed(self, thread_handler, conversation_info):
            """Test when a reply reference is removed"""
            message = {
                "message_id": "123",
                "orig_content": '@_**User|123** [said](https://zulip.at-hub.com/123-dm/near/456):\n```quote\nHello\n```\nOriginal reply',
                "content": 'Edited with no reply'
            }
            changed, thread_info = await thread_handler.update_thread_info(
                message, conversation_info
            )

            assert changed is True
            assert thread_info is None

        @pytest.mark.asyncio
        async def test_reply_added(self, thread_handler, conversation_info):
            """Test when a reply reference is added"""
            message = {
                "message_id": "123",
                "orig_content": 'Original with no reply',
                "content": '@_**User|123** [said](https://zulip.at-hub.com/123-dm/near/456):\n```quote\nHello\n```\nNow it\'s a reply'
            }

            with patch.object(
                ThreadHandler,
                "add_thread_info",
                return_value=ThreadInfo(thread_id="456", root_message_id="456")
            ):
                changed, thread_info = await thread_handler.update_thread_info(
                    message, conversation_info
                )

                assert changed is True
                assert thread_info is not None
                assert thread_info.thread_id == "456"

        @pytest.mark.asyncio
        async def test_reply_changed(self, thread_handler, conversation_info):
            """Test when a reply reference is changed to a different message"""
            message = {
                "message_id": "123",
                "orig_content": '@_**User|123** [said](https://zulip.at-hub.com/123-dm/near/456):\n```quote\nHello\n```\nOriginal reply',
                "content": '@_**User|123** [said](https://zulip.at-hub.com/123-dm/near/789):\n```quote\nHello\n```\nReplying to message#2'
            }

            with patch.object(
                ThreadHandler,
                "add_thread_info",
                return_value=ThreadInfo(thread_id="789", root_message_id="789")
            ):
                changed, thread_info = await thread_handler.update_thread_info(
                    message, conversation_info
                )

                assert changed is True
                assert thread_info is not None
                assert thread_info.thread_id == "789"

    class TestRemoveThreadInfo:
        """Tests for remove_thread_info method"""

        def test_remove_from_thread(self, thread_handler, conversation_info, cached_message):
            """Test removing a message from a thread that has multiple messages"""
            test_thread = ThreadInfo(
                thread_id="test_thread",
                root_message_id="root_message_id",
                messages=set(["123", "456"])
            )
            conversation_info.threads["test_thread"] = test_thread
            cached_message.thread_id = "test_thread"

            thread_handler.remove_thread_info(conversation_info, cached_message)

            assert "test_thread" in conversation_info.threads
            assert len(conversation_info.threads["test_thread"].messages) == 1

        def test_remove_last_message_from_thread(self, thread_handler, conversation_info, cached_message):
            """Test removing the last message from a thread"""
            test_thread = ThreadInfo(
                thread_id="test_thread",
                root_message_id="root_message_id",
                messages=set(["123"])
            )
            conversation_info.threads["test_thread"] = test_thread
            cached_message.thread_id = "test_thread"

            thread_handler.remove_thread_info(conversation_info, cached_message)

            assert "test_thread" not in conversation_info.threads
