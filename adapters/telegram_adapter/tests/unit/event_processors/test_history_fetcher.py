import pytest
import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from adapters.telegram_adapter.adapter.event_processors.history_fetcher import HistoryFetcher
from adapters.telegram_adapter.adapter.conversation.data_classes import ConversationInfo

class TestTelegramHistoryFetcher:
    """Tests for the Telegram HistoryFetcher class"""

    @pytest.fixture
    def telethon_client_mock(self):
        """Create a mocked Telegram client"""
        client = AsyncMock()
        client.__call__ = AsyncMock()
        return client

    @pytest.fixture
    def conversation_manager_mock(self):
        """Create a mocked conversation manager"""
        manager = AsyncMock()
        manager.get_conversation = MagicMock()
        manager.get_conversation_cache = MagicMock(return_value=[])
        manager.add_to_conversation = AsyncMock(return_value={"added_messages": []})
        manager.attachment_download_required = MagicMock(return_value=True)
        return manager

    @pytest.fixture
    def conversation_mock(self):
        """Create a mocked conversation"""
        conversation = MagicMock(spec=ConversationInfo)
        conversation.conversation_id = "123456789"
        return conversation

    @pytest.fixture
    def downloader_mock(self):
        """Create a mocked downloader"""
        downloader = AsyncMock()
        downloader.download_attachment = AsyncMock(return_value={
            "attachment_id": "test_attachment",
            "attachment_type": "document",
            "file_extension": "txt",
            "size": 1024
        })
        return downloader

    @pytest.fixture
    def rate_limiter_mock(self):
        """Create a mocked rate limiter"""
        limiter = AsyncMock()
        limiter.limit_request = AsyncMock()
        return limiter

    @pytest.fixture
    def mock_message(self):
        """Create a mock Telegram message"""
        message = MagicMock()
        message.id = 12345
        message.message = "Test message"
        message.date = datetime.now()

        # Mock for the sender
        from_id = MagicMock()
        from_id.user_id = 98765
        message.from_id = from_id

        # Mock for reply structure
        reply_to = MagicMock()
        reply_to.reply_to_msg_id = 54321
        message.reply_to = reply_to

        # Mock for media
        message.media = MagicMock()

        return message

    @pytest.fixture
    def mock_history_response(self, mock_message):
        """Create a mock history response from Telegram"""
        response = MagicMock()
        response.messages = [mock_message]

        # Add users to response
        user = MagicMock()
        user.id = 98765
        user.username = "test_user"
        user.first_name = "Test"
        user.last_name = "User"
        response.users = [user]

        return response

    @pytest.fixture
    def history_fetcher(self,
                        patch_config,
                        telethon_client_mock,
                        conversation_manager_mock,
                        conversation_mock,
                        downloader_mock,
                        rate_limiter_mock):
        """Create a HistoryFetcher instance"""
        conversation_manager_mock.get_conversation.return_value = conversation_mock

        fetcher = HistoryFetcher(
            config=patch_config,
            client=telethon_client_mock,
            conversation_manager=conversation_manager_mock,
            conversation_id="123456789",
            before=1627984000000,  # Example timestamp in milliseconds
            history_limit=10
        )
        fetcher.downloader = downloader_mock
        fetcher.rate_limiter = rate_limiter_mock

        return fetcher

    @pytest.mark.asyncio
    async def test_fetch_with_full_cache(self, history_fetcher):
        """Test fetch method when cache has enough messages"""
        cached_messages = []
        for i in range(10):  # history_limit is 10
            cached_messages.append({
                "message_id": f"100{i}",
                "conversation_id": "123456789",
                "sender": {"user_id": "98765", "display_name": "@test_user"},
                "text": f"Cached message {i}",
                "timestamp": 1627983900000 - i*1000,  # All before the 'before' timestamp
                "thread_id": None,
                "attachments": []
            })
        history_fetcher.conversation_manager.get_conversation_cache.return_value = cached_messages
        history_fetcher._fetch_from_api = AsyncMock()

        assert len(await history_fetcher.fetch()) == 10
        history_fetcher._fetch_from_api.assert_not_called() # API should not be called when cache has enough messages

    @pytest.mark.asyncio
    async def test_fetch_with_partial_cache(self, history_fetcher, mock_history_response):
        """Test fetch method when cache has some but not enough messages"""
        cached_messages = [
            {
                "message_id": "1001",
                "conversation_id": "123456789",
                "sender": {"user_id": "98765", "display_name": "@test_user"},
                "text": "Cached message",
                "timestamp": 1627983900000,  # Before the 'before' timestamp
                "thread_id": None,
                "attachments": []
            }
        ]
        history_fetcher.conversation_manager.get_conversation_cache.return_value = cached_messages
        history_fetcher.client.__call__.return_value = mock_history_response

        with patch.object(history_fetcher, '_fetch_from_api', return_value=[{
            "message_id": "12345",
            "conversation_id": "123456789",
            "sender": {"user_id": "98765", "display_name": "@test_user"},
            "text": "API message",
            "timestamp": 1627983800000,
            "thread_id": None,
            "attachments": []
        }]) as mock_fetch_api:
            result = await history_fetcher.fetch()

        mock_fetch_api.assert_called_once()

        assert len(result) == 2
        assert result[0]["message_id"] == "12345"
        assert result[1]["message_id"] == "1001"

    @pytest.mark.asyncio
    async def test_fetch_with_before_timestamp(self, history_fetcher):
        """Test _filter_and_limit_messages with before timestamp"""
        messages = [
            {
                "message_id": "1001",
                "conversation_id": "123456789",
                "timestamp": 1627984100000,  # After the 'before' timestamp
                "sender": {"user_id": "98765", "display_name": "@test_user"},
                "text": "Message 1",
                "thread_id": None,
                "attachments": []
            },
            {
                "message_id": "1002",
                "conversation_id": "123456789",
                "timestamp": 1627983900000,  # Before the 'before' timestamp
                "sender": {"user_id": "98765", "display_name": "@test_user"},
                "text": "Message 2",
                "thread_id": None,
                "attachments": []
            },
            {
                "message_id": "1003",
                "conversation_id": "123456789",
                "timestamp": 1627983800000,  # Before the 'before' timestamp
                "sender": {"user_id": "98765", "display_name": "@test_user"},
                "text": "Message 3",
                "thread_id": None,
                "attachments": []
            }
        ]

        result = history_fetcher._filter_and_limit_messages(messages)

        assert len(result) == 2
        assert result[0]["message_id"] == "1002"
        assert result[1]["message_id"] == "1003"

    @pytest.mark.asyncio
    async def test_fetch_with_after_timestamp(self, history_fetcher):
        """Test _filter_and_limit_messages with after timestamp"""
        history_fetcher.before = None
        history_fetcher.after = 1627983850000  # Example timestamp

        messages = [
            {
                "message_id": "1001",
                "conversation_id": "123456789",
                "timestamp": 1627984100000,  # After the 'after' timestamp
                "sender": {"user_id": "98765", "display_name": "@test_user"},
                "text": "Message 1",
                "thread_id": None,
                "attachments": []
            },
            {
                "message_id": "1002",
                "conversation_id": "123456789",
                "timestamp": 1627983900000,  # After the 'after' timestamp
                "sender": {"user_id": "98765", "display_name": "@test_user"},
                "text": "Message 2",
                "thread_id": None,
                "attachments": []
            },
            {
                "message_id": "1003",
                "conversation_id": "123456789",
                "timestamp": 1627983800000,  # Before the 'after' timestamp
                "sender": {"user_id": "98765", "display_name": "@test_user"},
                "text": "Message 3",
                "thread_id": None,
                "attachments": []
            }
        ]

        result = history_fetcher._filter_and_limit_messages(messages)

        assert len(result) == 2
        assert result[0]["message_id"] == "1001"
        assert result[1]["message_id"] == "1002"

    @pytest.mark.asyncio
    async def test_parse_fetched_history(self,
                                         history_fetcher,
                                         mock_history_response,
                                         mock_message):
        """Test _parse_fetched_history method"""
        past_date = datetime(2021, 7, 1, 12, 0, 0)  # July 1, 2021
        mock_message.date = past_date
        history_fetcher._get_users(mock_history_response)

        result = await history_fetcher._parse_fetched_history(mock_history_response)

        assert len(result) == 1
        assert result[0]["message_id"] == "12345"
        assert result[0]["conversation_id"] == "123456789"
        assert result[0]["text"] == "Test message"
        assert result[0]["thread_id"] == "54321"
        assert result[0]["sender"]["user_id"] == "98765"
        assert result[0]["sender"]["display_name"] == "@test_user"
        assert len(result[0]["attachments"]) == 1

    @pytest.mark.asyncio
    async def test_parse_and_store_fetched_history(self,
                                                   history_fetcher,
                                                   mock_history_response):
        """Test _parse_and_store_fetched_history method"""
        added_message = {
            "message_id": "12345",
            "conversation_id": "123456789",
            "text": "Test message",
            "timestamp": 1627983000000,
            "sender": {"user_id": "98765", "display_name": "@test_user"},
            "thread_id": "54321",
            "attachments": []
        }
        history_fetcher.conversation_manager.add_to_conversation.return_value = {
            "added_messages": [added_message]
        }

        result = await history_fetcher._parse_and_store_fetched_history(mock_history_response)

        history_fetcher.conversation_manager.add_to_conversation.assert_called_once()
        assert len(result) == 1
        assert result[0]["message_id"] == "12345"

    def test_get_users(self, history_fetcher, mock_history_response):
        """Test _get_users method"""
        history_fetcher._get_users(mock_history_response)

        assert 98765 in history_fetcher.users
        assert history_fetcher.users[98765].username == "test_user"

    @pytest.mark.asyncio
    async def test_update_limits(self, history_fetcher):
        """Test _update_limits method"""
        cached_messages = [
            {
                "message_id": "1001",
                "conversation_id": "123456789",
                "timestamp": 1627983900000,
                "sender": {"user_id": "98765", "display_name": "@test_user"},
                "text": "Cached message",
                "thread_id": None,
                "attachments": []
            }
        ]
        original_before = history_fetcher.before
        original_after = 1627983800000
        original_limit = history_fetcher.history_limit

        history_fetcher._update_limits(cached_messages)

        assert history_fetcher.before == 1627983900000  # Updated to cache message timestamp
        assert history_fetcher.before != original_before
        assert history_fetcher.history_limit == original_limit - 1  # Reduced by cache size

        history_fetcher.before = None
        history_fetcher.after = original_after
        history_fetcher.history_limit = original_limit
        history_fetcher._update_limits(cached_messages)

        assert history_fetcher.after == 1627983900000  # Updated to cache message timestamp
        assert history_fetcher.after != original_after
        assert history_fetcher.history_limit == original_limit - 1  # Reduced by cache size
