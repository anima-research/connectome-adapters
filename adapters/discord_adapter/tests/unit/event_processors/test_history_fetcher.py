import pytest
import asyncio
import discord

from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from adapters.discord_adapter.adapter.conversation.data_classes import ConversationInfo
from adapters.discord_adapter.adapter.conversation.manager import Manager
from adapters.discord_adapter.adapter.event_processors.history_fetcher import HistoryFetcher

class TestHistoryFetcher:
    """Tests for the Discord HistoryFetcher class"""

    @pytest.fixture
    def discord_client_mock(self):
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
    def downloader_mock(self):
        """Create a mocked downloader"""
        downloader = AsyncMock()
        downloader.download_attachment = AsyncMock()
        return downloader

    @pytest.fixture
    def conversation_manager_mock(self):
        """Create a mocked conversation manager"""
        manager = AsyncMock(spec=Manager)
        manager.get_conversation = MagicMock()
        manager.get_conversation_cache = MagicMock(return_value=[])
        manager.add_to_conversation = AsyncMock()
        return manager

    @pytest.fixture
    def mock_message_with_attachment(self):
        """Create a mock Discord message with attachment"""
        message = MagicMock(spec=discord.Message)
        message.id = 111222333
        message.content = "Message with attachment"
        message.created_at = datetime(2021, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
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
    def mock_attachments(self):
        """Create mock attachment data"""
        return [
            {
                "attachment_id": "987654",
                "attachment_type": "image",
                "filename": "987654.jpg",
                "content_type": "image/jpeg",
                "content": None,
                "size": 12345,
                "processable": True,
                "url": "https://example.com/test.jpg",
                "created_at": datetime(2021, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
            }
        ]

    @pytest.fixture
    def mock_formatted_messages(self,
                                mock_message_with_attachment,
                                mock_message_reply,
                                mock_attachments):
        """Create mock formatted message data"""
        return [
            {
                "message_id": str(mock_message_with_attachment.id),
                "conversation_id": "987654321",
                "sender": {
                    "user_id": str(mock_message_with_attachment.author.id),
                    "display_name": mock_message_with_attachment.author.display_name
                },
                "text": mock_message_with_attachment.content,
                "thread_id": None,
                "timestamp": int(mock_message_with_attachment.created_at.timestamp()),
                "attachments": mock_attachments
            },
            {
                "message_id": str(mock_message_reply.id),
                "conversation_id": "987654321",
                "sender": {
                    "user_id": str(mock_message_reply.author.id),
                    "display_name": mock_message_reply.author.display_name
                },
                "text": mock_message_reply.content,
                "thread_id": "111222333",
                "timestamp": int(mock_message_reply.created_at.timestamp()),
                "attachments": []
            }
        ]

    @pytest.fixture
    def mock_cached_messages(self):
        """Create mock cached message data"""
        return [
            {
                "message_id": "111222333",
                "conversation_id": "987654321",
                "sender": {
                    "user_id": "444555666",
                    "display_name": "Cool User"
                },
                "text": "Message with attachment",
                "thread_id": None,
                "timestamp": 1609502400,
                "attachments": []
            }
        ]

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
                        patch_config,
                        discord_client_mock,
                        conversation_manager_mock,
                        rate_limiter_mock,
                        downloader_mock,
                        mock_message_with_attachment,
                        mock_message_reply,
                        mock_formatted_messages,
                        mock_attachments):
        """Create a HistoryFetcher instance"""
        def _create(conversation_id, anchor=None, before=None, after=None, history_limit=None):
            if conversation_id == "987654321":
                conversation_manager_mock.get_conversation.return_value = ConversationInfo(
                    conversation_id="987654321",
                    conversation_type="channel",
                    conversation_name="general"
                )
            else:
                conversation_manager_mock.get_conversation.return_value = None

            fetcher = HistoryFetcher(
                config=patch_config,
                client=discord_client_mock,
                conversation_manager=conversation_manager_mock,
                conversation_id=conversation_id,
                anchor=anchor,
                before=before,
                after=after,
                history_limit=history_limit or 10
            )
            fetcher.downloader = downloader_mock
            fetcher.rate_limiter = rate_limiter_mock
            fetcher.conversation_manager.add_to_conversation.side_effect = [
                {"added_messages": [mock_formatted_messages[0]]},
                {"added_messages": [mock_formatted_messages[1]]}
            ]
            fetcher._download_attachments = AsyncMock(
                return_value={0: mock_attachments, 1: []}
            )
            fetcher._make_api_request = AsyncMock(
                return_value=[
                    mock_message_with_attachment,
                    mock_message_reply
                ]
            )

            return fetcher
        return _create

    @pytest.mark.asyncio
    async def test_fetch_with_anchor(self,
                                     history_fetcher,
                                     channel_mock,
                                     mock_attachments):
        """Test fetching history with an anchor"""
        fetcher = history_fetcher("987654321", anchor="222333444")
        history = await fetcher.fetch()

        assert len(history) == 2
        assert history[0]["message_id"] == "111222333"
        assert history[0]["conversation_id"] == "987654321"
        assert history[0]["sender"]["user_id"] == "444555666"
        assert history[0]["text"] == "Message with attachment"
        assert history[0]["attachments"] == mock_attachments

        assert history[1]["message_id"] == "444555666"
        assert history[1]["thread_id"] == "111222333"
        assert history[1]["timestamp"] == 1609504200

    @pytest.mark.asyncio
    async def test_fetch_with_before(self, history_fetcher):
        """Test fetching history with before timestamp"""
        fetcher = history_fetcher("987654321", before=1609504300)  # After both messages
        history = await fetcher.fetch()

        fetcher.conversation_manager.get_conversation_cache.assert_called_once()
        assert len(history) == 2  # Both messages are before the timestamp

    @pytest.mark.asyncio
    async def test_fetch_with_after(self,
                                    history_fetcher,
                                    channel_mock):
        """Test fetching history with after timestamp"""
        fetcher = history_fetcher("987654321", after=1609501000)  # Before both messages
        history = await fetcher.fetch()

        fetcher.conversation_manager.get_conversation_cache.assert_called_once()
        assert len(history) == 2  # Both messages are after the timestamp

    @pytest.mark.asyncio
    async def test_fetch_no_conversation(self, history_fetcher):
        """Test fetching history with no conversation"""
        fetcher = history_fetcher("nonexistent_id")
        assert await fetcher.fetch() == []

    def test_format_not_cached_message(self,
                                       history_fetcher,
                                       mock_message_with_attachment,
                                       mock_attachments):
        """Test formatting a message that isn't cached"""
        fetcher = history_fetcher("987654321")
        result = fetcher._format_not_cached_message(
            mock_message_with_attachment, mock_attachments
        )

        assert result["message_id"] == "111222333"
        assert result["conversation_id"] == "987654321"
        assert result["sender"]["user_id"] == "444555666"
        assert result["sender"]["display_name"] == "Cool User"
        assert result["text"] == "Message with attachment"
        assert result["thread_id"] is None
        assert result["timestamp"] == 1609502400

        assert len(result["attachments"]) == 1
        assert "created_at" not in result["attachments"][0]
        assert "attachment_id" in result["attachments"][0]
        assert "filename" in result["attachments"][0]
        assert "content_type" in result["attachments"][0]
        assert "url" in result["attachments"][0]
        assert "size" in result["attachments"][0]
        assert "processable" in result["attachments"][0]
        assert "content" in result["attachments"][0]
