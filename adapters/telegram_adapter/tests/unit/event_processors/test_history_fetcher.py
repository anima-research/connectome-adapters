import asyncio
import pytest

from datetime import datetime, timezone
from telethon import types
from unittest.mock import AsyncMock, MagicMock, patch

from adapters.telegram_adapter.adapter.event_processors.history_fetcher import HistoryFetcher

class TestHistoryFetcher:
    """Tests for the Telegram HistoryFetcher class"""

    @pytest.fixture
    def telegram_client_mock(self):
        """Create a mocked Telegram client"""
        client = AsyncMock()
        client.__call__ = AsyncMock()
        return client

    @pytest.fixture
    def rate_limiter_mock(self):
        """Create a mocked rate limiter"""
        limiter = AsyncMock()
        limiter.limit_request = AsyncMock()
        return limiter

    @pytest.fixture
    def downloader_mock(self):
        """Create a mocked downloader"""
        downloader = AsyncMock()
        downloader.download_attachment = AsyncMock(return_value={
            "attachment_id": "some_id",
            "attachment_type": "document",
            "filename": "some_id.txt",
            "size": 12345,
            "content_type": "text/plain",
            "content": "dGVzdAo=",
            "url": None,
            "created_at": datetime.now(),
            "processable": True
        })
        return downloader

    @pytest.fixture
    def conversation_manager_mock(self):
        """Create a mocked conversation manager"""
        manager = AsyncMock()
        manager.get_conversation = MagicMock()
        manager.get_conversation_cache = MagicMock(return_value=[])
        manager.add_to_conversation = AsyncMock()
        return manager

    @pytest.fixture
    def conversation_mock(self):
        """Create a mocked conversation"""
        conversation = MagicMock()
        conversation.conversation_id = "123456789"
        return conversation

    @pytest.fixture
    def mock_telegram_message(self):
        """Create a mock Telegram message"""
        msg = MagicMock(spec=types.Message)
        msg.id = 1001
        msg.message = "Test message"
        msg.date = datetime(2021, 8, 2, 12, 0, 0, tzinfo=timezone.utc)

        # Set up from_id
        from_id = MagicMock()
        from_id.user_id = 98765
        msg.from_id = from_id

        # Set up media
        msg.media = MagicMock()

        # Set up reply_to
        reply_to = MagicMock()
        reply_to.reply_to_msg_id = 1000
        msg.reply_to = reply_to

        return msg

    @pytest.fixture
    def mock_telegram_user(self):
        """Create a mock Telegram user"""
        user = MagicMock()
        user.id = 98765
        user.username = "testuser"
        user.first_name = "Test"
        user.last_name = "User"
        return user

    @pytest.fixture
    def mock_telegram_history(self, mock_telegram_message, mock_telegram_user):
        """Create a mock Telegram history response"""
        history = MagicMock()
        history.messages = [mock_telegram_message]
        history.users = [mock_telegram_user]
        return history

    @pytest.fixture
    def mock_formatted_message(self):
        """Create a mock formatted message"""
        return {
            "message_id": "1001",
            "conversation_id": "123456789",
            "sender": {
                "user_id": "98765",
                "display_name": "@testuser"
            },
            "text": "Test message",
            "thread_id": "1000",
            "timestamp": 1627905600000,  # 2021-08-02 12:00:00 UTC
            "attachments": [{
                "attachment_id": "some_id",
                "filename": "some_id.txt",
                "size": 12345,
                "content_type": "text/plain",
                "content": "dGVzdAo=",
                "url": None,
                "processable": True
            }]
        }

    @pytest.fixture
    def history_fetcher(self,
                        patch_config,
                        telegram_client_mock,
                        conversation_manager_mock,
                        rate_limiter_mock,
                        downloader_mock,
                        conversation_mock):
        """Create a HistoryFetcher instance"""
        def _create(conversation_id, anchor=None, before=None, after=None, history_limit=None):
            if conversation_id == "123456789":
                conversation_manager_mock.get_conversation.return_value = conversation_mock
            else:
                conversation_manager_mock.get_conversation.return_value = None

            fetcher = HistoryFetcher(
                config=patch_config,
                client=telegram_client_mock,
                conversation_manager=conversation_manager_mock,
                conversation_id=conversation_id,
                anchor=anchor,
                before=before,
                after=after,
                history_limit=history_limit or 10
            )
            fetcher.downloader = downloader_mock
            fetcher.rate_limiter = rate_limiter_mock
            fetcher._make_api_request = AsyncMock()

            return fetcher
        return _create

    @pytest.mark.asyncio
    async def test_fetch_with_anchor(self,
                                     history_fetcher,
                                     mock_telegram_history,
                                     mock_formatted_message):
        """Test fetching history with an anchor"""
        fetcher = history_fetcher("123456789", anchor="newest")
        fetcher._make_api_request.return_value = mock_telegram_history.messages

        fetcher.conversation_manager.add_to_conversation.return_value = {
            "added_messages": [mock_formatted_message]
        }

        history = await fetcher.fetch()

        assert len(history) == 1
        assert history[0]["message_id"] == "1001"
        assert history[0]["conversation_id"] == "123456789"

    @pytest.mark.asyncio
    async def test_fetch_with_before(self,
                                     history_fetcher,
                                     mock_telegram_history,
                                     mock_formatted_message):
        """Test fetching history with before timestamp"""
        fetcher = history_fetcher("123456789", before=1627910000000)
        fetcher._make_api_request.return_value = mock_telegram_history.messages
        fetcher.conversation_manager.add_to_conversation.return_value = {
            "added_messages": [mock_formatted_message]
        }

        history = await fetcher.fetch()

        assert len(history) == 1
        assert history[0]["message_id"] == "1001"

    @pytest.mark.asyncio
    async def test_fetch_with_after(self,
                                    history_fetcher,
                                    mock_telegram_history,
                                    mock_formatted_message):
        """Test fetching history with after timestamp"""
        fetcher = history_fetcher("123456789", after=1627900000000)

        with patch.object(
            fetcher, "_fetch_history_in_batches", new_callable=AsyncMock
        ) as mock_fetch_batches:
            mock_fetch_batches.return_value = [mock_telegram_history.messages[0]]
            fetcher.conversation_manager.add_to_conversation.return_value = {
                "added_messages": [mock_formatted_message]
            }

            history = await fetcher.fetch()

            mock_fetch_batches.assert_called_once()

            assert len(history) == 1
            assert history[0]["message_id"] == "1001"
            assert history[0]["timestamp"] > 1627900000000

    @pytest.mark.asyncio
    async def test_fetch_history_in_batches(self, history_fetcher):
        """Test _fetch_history_in_batches method with detailed debugging"""
        fetcher = history_fetcher("123456789", after=1627900000000)

        message2 = MagicMock()
        message2.id = 1002
        message2.date = datetime(2021, 8, 2, 13, 0, 0, tzinfo=timezone.utc)

        message1 = MagicMock()
        message1.id = 1001
        message1.date = datetime(2021, 8, 2, 12, 0, 0, tzinfo=timezone.utc)

        original_make_api_request = fetcher._make_api_request
        async def mock_api_request(limit, offset_id=0, offset_date=None):
            if offset_id == 0:
                return [message2]
            elif offset_id == 1002:
                return [message1]
            else:
                return []
        fetcher._make_api_request = mock_api_request

        assert len(await fetcher._fetch_history_in_batches()) == 2

        fetcher._make_api_request = original_make_api_request

    @pytest.mark.asyncio
    async def test_parse_fetched_history(self, history_fetcher, mock_telegram_message):
        """Test _parse_fetched_history method"""
        fetcher = history_fetcher("123456789")

        user = MagicMock()
        user.username = "testuser"
        fetcher.users = {98765: user}

        result = await fetcher._parse_fetched_history(
            [mock_telegram_message],
            {
                0: {
                    "attachment_id": "some_id",
                    "attachment_type": "document",
                    "filename": "some_id.txt",
                    "size": 12345,
                    "content_type": "text/plain",
                    "content": "dGVzdAo=",
                    "url": None,
                    "processable": True,
                    "created_at": datetime.now()
                }
            }
        )

        assert len(result) == 1
        assert result[0]["message_id"] == "1001"
        assert result[0]["sender"]["display_name"] == "@testuser"
        assert result[0]["text"] == "Test message"
        assert result[0]["thread_id"] == "1000"
        assert len(result[0]["attachments"]) == 1
        assert result[0]["attachments"][0]["attachment_id"] == "some_id"
        assert "attachment_type" not in result[0]["attachments"][0]
        assert "created_at" not in result[0]["attachments"][0]

    @pytest.mark.asyncio
    async def test_fetch_no_conversation(self, history_fetcher):
        """Test fetching history with no conversation"""
        fetcher = history_fetcher("nonexistent_id")
        assert await fetcher.fetch() == []
