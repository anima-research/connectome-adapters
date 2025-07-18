import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from src.core.cache.message_cache import MessageCache

class TestMessageCache:

    @pytest.fixture
    def config_mock(self):
        config = MagicMock()
        config.get_setting.side_effect = lambda section, key, default=None: {
            "caching": {
                "max_messages_per_conversation": 100,
                "max_total_messages": 1000,
                "cache_maintenance_interval": 300,
            }
        }.get(section, {}).get(key, default)
        return config

    @pytest.fixture
    def sample_message_info(self):
        return {
            "message_id": "123",
            "conversation_id": "456",
            "thread_id": None,
            "sender_id": "789",
            "sender_name": "Test User",
            "text": "Hello, world!",
            "timestamp": int(datetime.now().timestamp()),
            "edit_timestamp": None,
            "edited": False,
            "is_from_bot": False,
            "reply_to_message_id": None
        }

    @pytest.fixture
    def sample_messages_info(self):
        """Generate a list of sample messages with different timestamps"""
        messages = []
        base_time = datetime.now()

        for i in range(10):
            messages.append(
                {
                    "message_id": f"msg_{i}",
                    "conversation_id": "conv_1",
                    "thread_id": None,
                    "sender_id": "user_1",
                    "sender_name": "Test User",
                    "text": f"Message {i}",
                    "timestamp": int((base_time - timedelta(minutes=i)).timestamp()),
                    "edit_timestamp": None,
                    "edited": False,
                    "is_from_bot": False,
                    "reply_to_message_id": None
                }
            )

        for i in range(5):
            messages.append(
                {
                    "message_id": f"msg_conv2_{i}",
                    "conversation_id": "conv_2",
                    "thread_id": None,
                    "sender_id": "user_2",
                    "sender_name": "Another User",
                    "text": f"Message in conv 2: {i}",
                    "timestamp": int((base_time - timedelta(minutes=i)).timestamp()),
                    "edit_timestamp": None,
                    "edited": False,
                    "is_from_bot": True,
                    "reply_to_message_id": None
                }
            )

        return messages

    @pytest.fixture
    def message_cache(self, config_mock):
        """Create a message cache instance with mocked config"""
        return MessageCache(config_mock)

    class TestAddDeleteMessageFunctionality:
        """Tests for add and delete message functionality"""

        @pytest.mark.asyncio
        async def test_add_message(self, message_cache, sample_message_info):
            """Test adding a message to the cache"""
            await message_cache.add_message(sample_message_info)
            message = await message_cache.get_message_by_id(
                sample_message_info["conversation_id"], sample_message_info["message_id"]
            )

            assert message is not None
            assert message.message_id == sample_message_info["message_id"]
            assert message.text == sample_message_info["text"]

        @pytest.mark.asyncio
        async def test_delete_message(self, message_cache, sample_message_info):
            """Test deleting a message from the cache"""
            await message_cache.add_message(sample_message_info)
            assert await message_cache.get_message_by_id(
                sample_message_info["conversation_id"], sample_message_info["message_id"]
            ) is not None

            assert await message_cache.delete_message(
                sample_message_info["conversation_id"], sample_message_info["message_id"]
            ) is True
            assert await message_cache.get_message_by_id(
                sample_message_info["conversation_id"], sample_message_info["message_id"]
            ) is None

        @pytest.mark.asyncio
        async def test_delete_nonexistent_message(self, message_cache):
            """Test deleting a message that doesn't exist"""
            assert await message_cache.delete_message(
                "non_existent_conv", "non_existent_msg"
            ) is False

    class TestConversationMigrationFunctionality:
        """Tests for conversation migration functionality"""

        @pytest.mark.asyncio
        async def test_message_migration(self, message_cache, sample_messages_info):
            """Test migrating messages from one conversation to another"""
            for msg in sample_messages_info:
                if msg["conversation_id"] == "conv_1":
                    await message_cache.add_message(msg)

            await message_cache.migrate_message(
                "conv_1", "conv_3", sample_messages_info[0]["message_id"]
            )

            assert "conv_1" in message_cache.messages
            assert "conv_3" in message_cache.messages
            assert len(message_cache.messages["conv_3"]) == 1
            for _, msg in message_cache.messages["conv_3"].items():
                assert msg.conversation_id == "conv_3"

    class TestStorageLimitsFunctionality:
        """Tests for storage limits functionality"""

        @pytest.mark.asyncio
        async def test_conversation_limit_enforcement(self, message_cache, sample_messages_info):
            """Test that conversation message limits are enforced"""
            message_cache.max_messages_per_conversation = 5

            for msg in sample_messages_info:
                if msg["conversation_id"] == "conv_1":
                  await message_cache.add_message(msg)

            assert len(message_cache.messages["conv_1"]) > 5

            await message_cache._enforce_conversation_limit("conv_1")

            assert len(message_cache.messages["conv_1"]) == 5

            # Verify the newest messages are kept (lowest indices in our sample data)
            for i in range(5):
                assert f"msg_{i}" in message_cache.messages["conv_1"]

        @pytest.mark.asyncio
        async def test_total_limit_enforcement(self, message_cache, sample_messages_info):
            """Test that total message count limits are enforced"""
            message_cache.max_total_messages = 7

            for msg in sample_messages_info:
                await message_cache.add_message(msg)

            assert sum(len(msgs) for msgs in message_cache.messages.values()) > 7

            await message_cache._enforce_total_limit()

            assert sum(len(msgs) for msgs in message_cache.messages.values()) == 7

            # Verify the newest messages are kept (lowest indices in our sample data)
            assert "msg_0" in message_cache.messages["conv_1"]
            assert "msg_conv2_0" in message_cache.messages["conv_2"]
