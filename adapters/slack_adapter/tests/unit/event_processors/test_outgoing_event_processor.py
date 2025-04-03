import pytest
import os
import shutil
import emoji
from unittest.mock import AsyncMock, MagicMock, patch, call

from adapters.slack_adapter.adapter.attachment_loaders.uploader import Uploader
from adapters.slack_adapter.adapter.event_processors.outgoing_event_processor import OutgoingEventProcessor
from adapters.slack_adapter.adapter.event_processors.history_fetcher import HistoryFetcher
from core.event_processors.base_outgoing_event_processor import OutgoingEventType
from core.utils.emoji_converter import EmojiConverter

class TestOutgoingEventProcessor:
    """Tests for the Slack OutgoingEventProcessor class"""

    @pytest.fixture(scope="class", autouse=True)
    def ensure_test_directories(self):
        """Create necessary test directories before tests and clean up after"""
        os.makedirs("test_attachments", exist_ok=True)
        os.makedirs("test_attachments/document", exist_ok=True)

        yield

        if os.path.exists("test_attachments"):
            shutil.rmtree("test_attachments")

    @pytest.fixture
    def slack_client_mock(self):
        """Create a mocked Slack client"""
        client = AsyncMock()
        client.chat_postMessage = AsyncMock()
        client.chat_update = AsyncMock()
        client.chat_delete = AsyncMock()
        client.reactions_add = AsyncMock()
        client.reactions_remove = AsyncMock()
        return client

    @pytest.fixture
    def conversation_manager_mock(self):
        """Create a mocked conversation manager"""
        return AsyncMock()

    @pytest.fixture
    def rate_limiter_mock(self):
        """Create a mock rate limiter"""
        rate_limiter = AsyncMock()
        rate_limiter.limit_request = AsyncMock(return_value=None)
        rate_limiter.get_wait_time = AsyncMock(return_value=0)
        return rate_limiter

    @pytest.fixture
    def uploader_mock(self):
        """Create a mocked uploader"""
        uploader = AsyncMock(spec=Uploader)
        uploader.upload_attachments = AsyncMock(return_value=[])
        return uploader

    @pytest.fixture
    def processor(self,
                  patch_config,
                  slack_client_mock,
                  conversation_manager_mock,
                  rate_limiter_mock,
                  uploader_mock):
        """Create a SlackOutgoingEventProcessor with mocked dependencies"""
        processor = OutgoingEventProcessor(
            patch_config, slack_client_mock, conversation_manager_mock
        )
        processor.rate_limiter = rate_limiter_mock
        processor.uploader = uploader_mock
        return processor

    @pytest.fixture
    def history_fetcher_mock(self):
        """Create a mocked history fetcher"""
        fetcher = AsyncMock(spec=HistoryFetcher)
        fetcher.fetch = AsyncMock(return_value=[])
        return fetcher

    class TestProcessEvent:
        """Tests for the process_event method"""

        @pytest.mark.asyncio
        @pytest.mark.parametrize("event_type", [
            OutgoingEventType.SEND_MESSAGE,
            OutgoingEventType.EDIT_MESSAGE,
            OutgoingEventType.DELETE_MESSAGE,
            OutgoingEventType.ADD_REACTION,
            OutgoingEventType.REMOVE_REACTION,
            OutgoingEventType.FETCH_HISTORY
        ])
        async def test_process_event_calls_correct_handler(self, processor, event_type):
            """Test that process_event calls the correct handler method"""
            data = {"test": "data"}
            handler_mocks = {}

            for handler_type in OutgoingEventType:
                method_name = f"_handle_{handler_type.value}_event"
                handler_mock = AsyncMock(return_value={"request_completed": True})
                handler_mocks[handler_type] = handler_mock
                setattr(processor, method_name, handler_mock)

            response = await processor.process_event(event_type, data)
            assert response["request_completed"] is True
            handler_mocks[event_type].assert_called_once_with(data)

        @pytest.mark.asyncio
        async def test_process_unknown_event_type(self, processor):
            """Test handling an unknown event type"""
            response = await processor.process_event("unknown_type", {})
            assert response["request_completed"] is False

    class TestSendMessage:
        """Tests for the send_message method"""

        @pytest.mark.asyncio
        async def test_send_message_success(self, processor, slack_client_mock):
            """Test sending a simple message successfully"""
            slack_client_mock.chat_postMessage.return_value = {
                "ok": True,
                "ts": "1662031200.123456"
            }

            response = await processor._handle_send_message_event({
                "conversation_id": "T12345/C123456789",
                "text": "Hello, world!"
            })

            assert response["request_completed"] is True
            assert response["message_ids"] == ["1662031200.123456"]

            processor.rate_limiter.limit_request.assert_called_once_with(
                "message", "T12345/C123456789"
            )
            slack_client_mock.chat_postMessage.assert_called_once_with(
                channel="C123456789",
                text="Hello, world!",
                unfurl_links=False,
                unfurl_media=False
            )

        @pytest.mark.asyncio
        async def test_send_message_long_text(self, processor, slack_client_mock):
            """Test sending a message with text longer than max length"""
            slack_client_mock.chat_postMessage.side_effect = [
                {"ok": True, "ts": "1662031200.123456"},
                {"ok": True, "ts": "1662031201.123457"}
            ]

            data = {
                "conversation_id": "T12345/C123456789",
                "text": "This is a very long message " * 100  # Very long message
            }

            with patch.object(processor, "_split_long_message", return_value=["Part 1", "Part 2"]):
                response = await processor._handle_send_message_event(data)

                assert response["request_completed"] is True
                assert response["message_ids"] == ["1662031200.123456", "1662031201.123457"]

                assert slack_client_mock.chat_postMessage.call_count == 2
                slack_client_mock.chat_postMessage.assert_has_calls([
                    call(channel="C123456789", text="Part 1", unfurl_links=False, unfurl_media=False),
                    call(channel="C123456789", text="Part 2", unfurl_links=False, unfurl_media=False)
                ])

        @pytest.mark.asyncio
        async def test_send_message_with_attachments(self, processor, slack_client_mock):
            """Test sending a message with attachments"""
            slack_client_mock.chat_postMessage.return_value = {"ok": True, "ts": "1662031200.123456"}

            attachments = [
                {
                    "attachment_type": "document",
                    "file_path": "test_attachments/document/file1.txt",
                    "size": 100
                }
            ]
            data = {
                "conversation_id": "T12345/C123456789",
                "text": "Message with attachments",
                "attachments": attachments
            }

            response = await processor._handle_send_message_event(data)

            assert response["request_completed"] is True
            assert response["message_ids"] == ["1662031200.123456"]

            processor.uploader.upload_attachments.assert_called_once_with(
                "T12345/C123456789", attachments
            )

        @pytest.mark.asyncio
        async def test_handle_send_message_missing_fields(self, processor):
            """Test handling missing fields in send message request"""
            # Missing 'text' field
            data = {"conversation_id": "T12345/C123456789"}

            response = await processor._handle_send_message_event(data)
            assert response["request_completed"] is False

            # Missing 'conversation_id' field
            data = {"text": "Hello, world!"}

            response = await processor._handle_send_message_event(data)
            assert response["request_completed"] is False

    class TestEditMessage:
        """Tests for the edit_message method"""

        @pytest.mark.asyncio
        async def test_edit_message_success(self, processor, slack_client_mock):
            """Test successfully editing a message"""
            slack_client_mock.chat_update.return_value = {"ok": True}

            data = {
                "conversation_id": "T12345/C123456789",
                "message_id": "1662031200.123456",
                "text": "Updated text"
            }

            response = await processor._handle_edit_message_event(data)

            assert response["request_completed"] is True
            processor.rate_limiter.limit_request.assert_called_once_with(
                "edit_message", "T12345/C123456789"
            )
            slack_client_mock.chat_update.assert_called_once_with(
                channel="C123456789",
                ts="1662031200.123456",
                text="Updated text"
            )

        @pytest.mark.asyncio
        async def test_handle_edit_message_missing_fields(self, processor):
            """Test handling missing fields in edit message request"""
            # Missing 'text' field
            data = {
                "conversation_id": "T12345/C123456789",
                "message_id": "1662031200.123456"
            }

            response = await processor._handle_edit_message_event(data)
            assert response["request_completed"] is False

            # Missing 'message_id' field
            data = {
                "conversation_id": "T12345/C123456789",
                "text": "Updated text"
            }

            response = await processor._handle_edit_message_event(data)
            assert response["request_completed"] is False

            # Missing 'conversation_id' field
            data = {
                "message_id": "1662031200.123456",
                "text": "Updated text"
            }

            response = await processor._handle_edit_message_event(data)
            assert response["request_completed"] is False

    class TestDeleteMessage:
        """Tests for the delete_message method"""

        @pytest.mark.asyncio
        async def test_delete_message_success(self, processor, slack_client_mock):
            """Test successfully deleting a message"""
            slack_client_mock.chat_delete.return_value = {"ok": True}

            data = {
                "conversation_id": "T12345/C123456789",
                "message_id": "1662031200.123456"
            }

            response = await processor._handle_delete_message_event(data)

            assert response["request_completed"] is True
            processor.rate_limiter.limit_request.assert_called_once_with(
                "delete_message", "T12345/C123456789"
            )
            slack_client_mock.chat_delete.assert_called_once_with(
                channel="C123456789",
                ts="1662031200.123456"
            )

        @pytest.mark.asyncio
        async def test_handle_delete_message_missing_fields(self, processor):
            """Test handling missing fields in delete message request"""
            # Missing 'message_id' field
            data = {"conversation_id": "T12345/C123456789"}

            response = await processor._handle_delete_message_event(data)
            assert response["request_completed"] is False

            # Missing 'conversation_id' field
            data = {"message_id": "1662031200.123456"}

            response = await processor._handle_delete_message_event(data)
            assert response["request_completed"] is False

    class TestReactions:
        """Tests for the reaction-related methods"""

        @pytest.mark.asyncio
        async def test_add_reaction_success(self, processor, slack_client_mock):
            """Test successfully adding a reaction"""
            slack_client_mock.reactions_add.return_value = {"ok": True}

            data = {
                "conversation_id": "T12345/C123456789",
                "message_id": "1662031200.123456",
                "emoji": "thumbs_up"
            }

            with patch.object(EmojiConverter, "standard_to_platform_specific", return_value="+1"):
                response = await processor._handle_add_reaction_event(data)

                assert response["request_completed"] is True
                processor.rate_limiter.limit_request.assert_called_once_with(
                    "add_reaction", "T12345/C123456789"
                )
                slack_client_mock.reactions_add.assert_called_once_with(
                    channel="C123456789",
                    timestamp="1662031200.123456",
                    name="+1"  # Using mock converter's behavior
                )

        @pytest.mark.asyncio
        async def test_remove_reaction_success(self, processor, slack_client_mock):
            """Test successfully removing a reaction"""
            slack_client_mock.reactions_remove.return_value = {"ok": True}

            data = {
                "conversation_id": "T12345/C123456789",
                "message_id": "1662031200.123456",
                "emoji": "thumbs_up"
            }

            with patch.object(EmojiConverter, "standard_to_platform_specific", return_value="+1"):
                response = await processor._handle_remove_reaction_event(data)

                assert response["request_completed"] is True

                processor.rate_limiter.limit_request.assert_called_once_with(
                    "remove_reaction", "T12345/C123456789"
                )
                slack_client_mock.reactions_remove.assert_called_once_with(
                    channel="C123456789",
                    timestamp="1662031200.123456",
                    name="+1"  # Using mock converter's behavior
                )

    class TestFetchHistory:
        """Tests for the fetch_history method"""

        @pytest.mark.asyncio
        @pytest.mark.filterwarnings("ignore::RuntimeWarning")
        async def test_fetch_history_before(self, processor):
            """Test fetching history with 'before' parameter"""
            data = {
                "conversation_id": "T12345/C123456789",
                "before": 1662031200000,  # millisecond timestamp
                "limit": 10
            }
            mock_history = [{"message": "test"}]

            with patch.object(HistoryFetcher, "fetch", return_value=mock_history):
                response = await processor._handle_fetch_history_event(data)

                assert response["request_completed"] is True
                assert response["history"] == mock_history

        @pytest.mark.asyncio
        @pytest.mark.filterwarnings("ignore::RuntimeWarning")
        async def test_fetch_history_after(self, processor):
            """Test fetching history with 'after' parameter"""
            data = {
                "conversation_id": "T12345/C123456789",
                "after": 1662031200000,  # millisecond timestamp
                "limit": 10
            }
            mock_history = [{"message": "test"}]

            with patch.object(HistoryFetcher, "fetch", return_value=mock_history):
                response = await processor._handle_fetch_history_event(data)

                assert response["request_completed"] is True
                assert response["history"] == mock_history

        @pytest.mark.asyncio
        async def test_fetch_history_missing_parameters(self, processor):
            """Test fetching history with missing before/after parameters"""
            data = {
                "conversation_id": "T12345/C123456789",
                "limit": 10
            }
            response = await processor._handle_fetch_history_event(data)

            assert response["request_completed"] is False

        @pytest.mark.asyncio
        async def test_handle_fetch_history_missing_conversation_id(self, processor):
            """Test handling missing conversation_id in fetch history request"""
            data = {
                "before": 1662031200000,
                "limit": 10
            }
            response = await processor._handle_fetch_history_event(data)

            assert response["request_completed"] is False
