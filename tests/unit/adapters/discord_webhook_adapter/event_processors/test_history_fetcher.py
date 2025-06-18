import pytest
import asyncio
import discord

from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from src.adapters.discord_webhook_adapter.conversation.manager import Manager
from src.adapters.discord_webhook_adapter.event_processors.history_fetcher import HistoryFetcher

class TestHistoryFetcher:
    """Tests for the Discord HistoryFetcher class"""

    @pytest.fixture
    def discord_webhook_client_mock(self):
        """Create a mocked Discord client"""
        client = MagicMock()
        return client

    @pytest.fixture
    def rate_limiter_mock(self):
        """Create a mocked rate limiter"""
        limiter = AsyncMock()
        limiter.limit_request = AsyncMock()
        return limiter

    @pytest.fixture
    def conversation_manager_mock(self):
        """Create a mocked conversation manager"""
        manager = AsyncMock(spec=Manager)
        manager.get_conversation = MagicMock()
        return manager

    @pytest.fixture
    def mock_message_with_attachment(self):
        """Create a mock Discord message with attachment"""
        message = MagicMock(spec=discord.Message)
        message.id = 111222333
        message.content = "Message with attachment"
        message.created_at = datetime(2021, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        message.edited_at = None
        message.type = discord.MessageType.default

        author = MagicMock()
        author.id = 444555666
        author.name = "User One"
        author.display_name = "Cool User"
        message.author = author

        attachment = MagicMock(spec=discord.Attachment)
        attachment.id = 987654
        attachment.filename = "test.jpg"
        attachment.url = "https://example.com/test.jpg"
        attachment.size = 12345
        message.attachments = [attachment]

        message.reference = None
        return message

    @pytest.fixture
    def mock_message_reply(self):
        """Create a mock Discord message that's a reply"""
        message = MagicMock(spec=discord.Message)
        message.id = 444555666
        message.content = "This is a reply"
        message.created_at = datetime(2021, 1, 1, 12, 30, 0, tzinfo=timezone.utc)
        message.edited_at = None
        message.type = discord.MessageType.default

        author = MagicMock()
        author.id = 777888999
        author.name = "User Two"
        author.display_name = "User 2"
        message.author = author

        message.attachments = []

        reference = MagicMock()
        reference.message_id = 111222333
        message.reference = reference
        return message

    @pytest.fixture
    def channel_mock(self, mock_message_with_attachment, mock_message_reply):
        """Create a mocked Discord channel"""
        history = MagicMock()
        history.return_value = MagicMock()
        history.return_value.flatten = AsyncMock(
            return_value=[mock_message_with_attachment, mock_message_reply]
        )

        channel = AsyncMock()
        channel.history = history

        return channel

    @pytest.fixture
    def history_fetcher(self,
                        discord_webhook_config,
                        discord_webhook_client_mock,
                        conversation_manager_mock,
                        rate_limiter_mock,
                        mock_message_with_attachment,
                        mock_message_reply):
        """Create a HistoryFetcher instance"""
        def _create(conversation_id, anchor=None, before=None, after=None, history_limit=None):
            conversation_manager_mock.get_conversation.return_value = None

            fetcher = HistoryFetcher(
                config=discord_webhook_config,
                client=discord_webhook_client_mock,
                conversation_manager=conversation_manager_mock,
                conversation_id=conversation_id,
                anchor=anchor,
                before=before,
                after=after,
                history_limit=history_limit or 10
            )
            fetcher.rate_limiter = rate_limiter_mock
            fetcher._make_api_request = AsyncMock(
                return_value=[
                    mock_message_with_attachment,
                    mock_message_reply
                ]
            )

            return fetcher
        return _create

    @pytest.mark.asyncio
    async def test_fetch_with_before(self, history_fetcher):
        """Test fetching history with before timestamp"""
        fetcher = history_fetcher("987654321", before=1609504300)  # After both messages
        history = await fetcher.fetch()

        assert len(history) == 2  # Both messages are before the timestamp

    @pytest.mark.asyncio
    async def test_fetch_with_after(self, history_fetcher):
        """Test fetching history with after timestamp"""
        fetcher = history_fetcher("987654321", after=1609501000)  # Before both messages
        history = await fetcher.fetch()

        assert len(history) == 2  # Both messages are after the timestamp

    @pytest.mark.asyncio
    async def test_fetch_no_conversation(self, history_fetcher):
        """Test fetching history with no conversation"""
        fetcher = history_fetcher("nonexistent_id")
        assert await fetcher.fetch() == []

    def test_format_message(self, history_fetcher, mock_message_with_attachment):
        """Test formatting a message that isn't cached"""
        fetcher = history_fetcher("987654321")
        result = fetcher._format_message(mock_message_with_attachment)

        assert result["message_id"] == "111222333"
        assert result["conversation_id"] == "987654321"
        assert result["sender"]["user_id"] == "444555666"
        assert result["sender"]["display_name"] == "Cool User"
        assert result["text"] == "Message with attachment"
        assert result["thread_id"] is None
        assert result["timestamp"] == 1609502400
        assert result["edit_timestamp"] is None
        assert result["edited"] is False
        assert len(result["attachments"]) == 0
