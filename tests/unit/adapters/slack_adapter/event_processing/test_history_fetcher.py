import pytest
import asyncio

from unittest.mock import AsyncMock, MagicMock, patch

from src.adapters.slack_adapter.conversation.data_classes import ConversationInfo
from src.adapters.slack_adapter.conversation.manager import Manager
from src.adapters.slack_adapter.event_processing.attachment_loaders.downloader import Downloader
from src.adapters.slack_adapter.event_processing.history_fetcher import HistoryFetcher

class TestHistoryFetcher:
    """Tests for the Slack HistoryFetcher class"""

    @pytest.fixture
    def slack_client_mock(self):
        """Create a mocked Slack client"""
        client = AsyncMock()
        client.conversations_history = AsyncMock()
        client.users_info = AsyncMock()
        return client

    @pytest.fixture
    def downloader_mock(self):
        """Create a mocked downloader"""
        downloader = AsyncMock(spec=Downloader)
        downloader.download_attachments = AsyncMock()
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
    def mock_slack_message_with_attachment(self):
        """Create a mock Slack message with attachment"""
        return {
            "type": "message",
            "ts": "1609502400.000123",
            "text": "Message with attachment",
            "user": "U444555666",
            "team": "T123",
            "files": [
                {
                    "id": "F987654",
                    "name": "test.jpg",
                    "url_private": "https://files.slack.com/files-pri/T123456/test.jpg",
                    "size": 12345,
                    "mimetype": "image/jpeg"
                }
            ]
        }

    @pytest.fixture
    def mock_slack_message_reply(self):
        """Create a mock Slack message that's a reply"""
        return {
            "type": "message",
            "ts": "1609504200.000456",
            "text": "This is a reply",
            "user": "U777888999",
            "team": "T123",
            "thread_ts": "1609502400.000123"
        }

    @pytest.fixture
    def mock_slack_history_response(self, mock_slack_message_with_attachment, mock_slack_message_reply):
        """Create a mock Slack history response"""
        return {
            "ok": True,
            "messages": [mock_slack_message_reply, mock_slack_message_with_attachment],
            "has_more": False
        }

    @pytest.fixture
    def mock_user_info_response(self):
        """Create a mock user info response"""
        return {
            "ok": True,
            "user": {
                "id": "U444555666",
                "name": "cooluser",
                "real_name": "Cool User"
            }
        }

    @pytest.fixture
    def mock_attachments(self):
        """Create mock attachment data"""
        return [
            {
                "attachment_id": "F987654",
                "filename": "test.jpg",
                "size": 12345,
                "content_type": "image/jpeg",
                "content": None,
                "url": "https://files.slack.com/files-pri/T123456/test.jpg",
                "processable": True
            }
        ]

    @pytest.fixture
    def standard_conversation_id(self):
        """Create a mock standard conversation ID"""
        return "slack_F0OIohoDYwVnEyYccO7j"

    @pytest.fixture
    def mock_formatted_messages(self,
                                mock_slack_message_with_attachment,
                                mock_slack_message_reply,
                                mock_attachments,
                                standard_conversation_id):
        """Create mock formatted message data"""
        return [
            {
                "message_id": mock_slack_message_with_attachment["ts"],
                "conversation_id": standard_conversation_id,
                "sender": {
                    "user_id": mock_slack_message_with_attachment["user"],
                    "display_name": "Cool User"
                },
                "text": mock_slack_message_with_attachment["text"],
                "thread_id": None,
                "timestamp": int(float(mock_slack_message_with_attachment["ts"])),
                "attachments": mock_attachments,
                "is_direct_message": False,
                "mentions": []
            },
            {
                "message_id": mock_slack_message_reply["ts"],
                "conversation_id": standard_conversation_id,
                "sender": {
                    "user_id": mock_slack_message_reply["user"],
                    "display_name": "User Two"
                },
                "text": mock_slack_message_reply["text"],
                "thread_id": mock_slack_message_reply["thread_ts"],
                "timestamp": int(float(mock_slack_message_reply["ts"])),
                "attachments": [],
                "is_direct_message": False,
                "mentions": []
            }
        ]

    @pytest.fixture
    def mock_cached_messages(self, standard_conversation_id):
        """Create mock cached message data"""
        return [
            {
                "message_id": "1609502400.000123",
                "conversation_id": standard_conversation_id,
                "sender": {
                    "user_id": "U444555666",
                    "display_name": "Cool User"
                },
                "text": "Message with attachment",
                "thread_id": None,
                "timestamp": 1609502400,
                "attachments": []
            }
        ]

    @pytest.fixture
    def history_fetcher(self,
                        slack_config,
                        slack_client_mock,
                        conversation_manager_mock,
                        rate_limiter_mock,
                        downloader_mock,
                        mock_slack_history_response,
                        mock_formatted_messages,
                        mock_attachments,
                        mock_user_info_response,
                        standard_conversation_id):
        """Create a HistoryFetcher instance"""
        def _create(conversation_id, anchor=None, before=None, after=None, history_limit=None):
            if conversation_id == standard_conversation_id:
                conversation_manager_mock.get_conversation.return_value = ConversationInfo(
                    platform_conversation_id="T123/C456",
                    conversation_id=standard_conversation_id,
                    conversation_type="channel"
                )
            else:
                conversation_manager_mock.get_conversation.return_value = None

            fetcher = HistoryFetcher(
                config=slack_config,
                client=slack_client_mock,
                conversation_manager=conversation_manager_mock,
                conversation_id=conversation_id,
                anchor=anchor,
                before=before,
                after=after,
                history_limit=history_limit or 10
            )

            # Set up mocks
            fetcher.downloader = downloader_mock
            fetcher.rate_limiter = rate_limiter_mock
            fetcher.conversation_manager.add_to_conversation.side_effect = [
                {"added_messages": [mock_formatted_messages[0]]},
                {"added_messages": [mock_formatted_messages[1]]}
            ]

            # Configure client mock responses
            slack_client_mock.conversations_history.return_value = mock_slack_history_response
            slack_client_mock.users_info.return_value = mock_user_info_response

            # Mock internal methods
            fetcher._download_attachments = AsyncMock(
                return_value={0: mock_attachments, 1: []}
            )

            return fetcher

        return _create

    @pytest.mark.asyncio
    async def test_fetch_with_anchor(self,
                                     history_fetcher,
                                     slack_client_mock,
                                     mock_attachments,
                                     standard_conversation_id):
        """Test fetching history with an anchor"""
        fetcher = history_fetcher(standard_conversation_id, anchor="1609504300.000789")
        history = await fetcher.fetch()

        slack_client_mock.conversations_history.assert_called_with(
            channel="C456",
            limit=10,
            latest="1609504300.000789",
            inclusive=False
        )

        assert len(history) == 2
        assert history[0]["message_id"] == "1609502400.000123"
        assert history[0]["conversation_id"] == standard_conversation_id
        assert history[0]["sender"]["user_id"] == "U444555666"
        assert history[0]["text"] == "Message with attachment"
        assert history[0]["attachments"] == mock_attachments

        assert history[1]["message_id"] == "1609504200.000456"
        assert history[1]["thread_id"] == "1609502400.000123"
        assert history[1]["timestamp"] == 1609504200

    @pytest.mark.asyncio
    async def test_fetch_with_before(self, history_fetcher, slack_client_mock, standard_conversation_id):
        """Test fetching history with before timestamp"""
        before_timestamp = 1609504300  # After both test messages
        fetcher = history_fetcher(standard_conversation_id, before=before_timestamp)
        history = await fetcher.fetch()

        # Check API call parameters
        slack_client_mock.conversations_history.assert_called_with(
            channel="C456",
            limit=10,
            latest="1609504300.000000",
            inclusive=False
        )

        # Both messages should appear in the results
        assert len(history) == 2

    @pytest.mark.asyncio
    async def test_fetch_with_after(self, history_fetcher, slack_client_mock, standard_conversation_id):
        """Test fetching history with after timestamp"""
        after_timestamp = 1609501000  # Before both test messages
        fetcher = history_fetcher(standard_conversation_id, after=after_timestamp)
        history = await fetcher.fetch()

        # Check API call parameters
        slack_client_mock.conversations_history.assert_called_with(
            channel="C456",
            limit=10,
            oldest="1609501000.000000",
            inclusive=False
        )

        # Both messages should appear in the results
        assert len(history) == 2

    @pytest.mark.asyncio
    async def test_fetch_no_conversation(self, history_fetcher):
        """Test fetching history with no conversation"""
        fetcher = history_fetcher("nonexistent_id")
        assert await fetcher.fetch() == []

    @pytest.mark.asyncio
    async def test_fetch_from_cache(self, history_fetcher, mock_cached_messages, standard_conversation_id):
        """Test fetching from cache"""
        fetcher = history_fetcher(standard_conversation_id, before=1609502500)
        fetcher.conversation_manager.get_conversation_cache.return_value = mock_cached_messages
        fetcher.cache_fetched_history = True

        result = await fetcher.fetch()

        # Should have called get_conversation_cache
        fetcher.conversation_manager.get_conversation_cache.assert_called_once()

        # Should have returned the cached message
        assert len(result) == 1
        assert result[0]["message_id"] == "1609502400.000123"

    @pytest.mark.asyncio
    async def test_parse_fetched_history_with_cache(self,
                                                    history_fetcher,
                                                    mock_slack_message_with_attachment,
                                                    mock_slack_message_reply,
                                                    mock_formatted_messages,
                                                    standard_conversation_id):
        """Test parsing fetched history with caching enabled"""
        fetcher = history_fetcher(standard_conversation_id)
        fetcher.cache_fetched_history = True

        result = await fetcher._parse_fetched_history([
            mock_slack_message_with_attachment,
            mock_slack_message_reply
        ])

        assert fetcher.conversation_manager.add_to_conversation.call_count == 2

        # First call should include the attachment
        first_call_args = fetcher.conversation_manager.add_to_conversation.call_args_list[0][0][0]
        assert first_call_args["message"] == mock_slack_message_with_attachment
        assert first_call_args["attachments"] == mock_formatted_messages[0]["attachments"]

        # Should return formatted messages
        assert len(result) == 2
        assert result[0]["message_id"] == mock_formatted_messages[0]["message_id"]
        assert result[1]["message_id"] == mock_formatted_messages[1]["message_id"]

    @pytest.mark.asyncio
    async def test_parse_fetched_history_without_cache(self,
                                                       history_fetcher,
                                                       mock_slack_message_with_attachment,
                                                       mock_slack_message_reply,
                                                       standard_conversation_id):
        """Test parsing fetched history without caching"""
        fetcher = history_fetcher(standard_conversation_id)
        fetcher.cache_fetched_history = False

        with patch.object(fetcher, "_format_not_cached_message") as mock_format:
            mock_format.side_effect = [
                {"message_id": "1609502400.000123"},
                {"message_id": "1609504200.000456"}
            ]

            result = await fetcher._parse_fetched_history([
                mock_slack_message_with_attachment,
                mock_slack_message_reply
            ])

            # Should not have called add_to_conversation
            fetcher.conversation_manager.add_to_conversation.assert_not_called()

            # Should have called _format_not_cached_message twice
            assert mock_format.call_count == 2
            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_user_info(self,
                                 history_fetcher,
                                 slack_client_mock,
                                 mock_user_info_response,
                                 rate_limiter_mock,
                                 standard_conversation_id):
        """Test getting user info"""
        fetcher = history_fetcher(standard_conversation_id)
        slack_client_mock.users_info.return_value = mock_user_info_response

        # First call - should fetch from API
        user_info = await fetcher._get_user_info({"user": "U444555666"})

        rate_limiter_mock.limit_request.assert_called_once_with("get_user_info")
        slack_client_mock.users_info.assert_called_once_with(user="U444555666")
        assert user_info == mock_user_info_response["user"]

        rate_limiter_mock.limit_request.reset_mock()
        slack_client_mock.users_info.reset_mock()

        # Second call - should use cache
        user_info = await fetcher._get_user_info({"user": "U444555666"})

        rate_limiter_mock.limit_request.assert_not_called()
        slack_client_mock.users_info.assert_not_called()
        assert user_info == mock_user_info_response["user"]

    def test_format_not_cached_message(self,
                                       history_fetcher,
                                       mock_slack_message_with_attachment,
                                       mock_attachments,
                                       standard_conversation_id):
        """Test formatting a message that isn't cached"""
        fetcher = history_fetcher(standard_conversation_id)
        user_info = {"name": "Cool User"}

        result = fetcher._format_not_cached_message(
            mock_slack_message_with_attachment,
            mock_attachments,
            user_info
        )

        assert result["message_id"] == "1609502400.000123"
        assert result["conversation_id"] == standard_conversation_id
        assert result["sender"]["user_id"] == "U444555666"
        assert result["sender"]["display_name"] == "Cool User"
        assert result["text"] == "Message with attachment"
        assert result["thread_id"] is None
        assert result["timestamp"] == 1609502400
        assert result["attachments"] == mock_attachments

    @pytest.mark.asyncio
    async def test_fetch_from_api_error_handling(self, history_fetcher, standard_conversation_id):
        """Test error handling in _fetch_from_api"""
        fetcher = history_fetcher(standard_conversation_id, before=1609504300)

        with patch.object(fetcher, "_fetch_history_in_batches", side_effect=Exception("Test error")):
            assert await fetcher._fetch_from_api() == []
