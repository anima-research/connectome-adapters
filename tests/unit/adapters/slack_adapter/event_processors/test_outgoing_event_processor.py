import emoji
import os
import pytest

from unittest.mock import AsyncMock, MagicMock, patch, call
from src.adapters.slack_adapter.attachment_loaders.uploader import Uploader
from src.adapters.slack_adapter.event_processors.outgoing_event_processor import OutgoingEventProcessor
from src.adapters.slack_adapter.event_processors.history_fetcher import HistoryFetcher
from src.core.utils.emoji_converter import EmojiConverter

class TestOutgoingEventProcessor:
    """Tests for the Slack OutgoingEventProcessor class"""

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
        manager = AsyncMock()
        manager.get_conversation = MagicMock()
        manager.get_conversation_member = MagicMock()
        return manager

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
                  slack_config,
                  slack_client_mock,
                  conversation_manager_mock,
                  rate_limiter_mock,
                  uploader_mock):
        """Create a SlackOutgoingEventProcessor with mocked dependencies"""
        processor = OutgoingEventProcessor(
            slack_config, slack_client_mock, conversation_manager_mock
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

    class TestSendMessage:
        """Tests for the send_message method"""

        @pytest.mark.asyncio
        async def test_send_message_success(self, processor, slack_client_mock):
            """Test sending a simple message successfully"""
            slack_client_mock.chat_postMessage.return_value = {
                "ok": True,
                "ts": "1662031200.123456"
            }

            response = await processor.process_event({
                "event_type": "send_message",
                "data": {
                    "conversation_id": "T12345/C123456789",
                    "text": "Hello, world!"
                }
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

            with patch.object(processor, "_split_long_message", return_value=["Part 1", "Part 2"]):
                response = await processor.process_event({
                    "event_type": "send_message",
                    "data": {
                        "conversation_id": "T12345/C123456789",
                        "text": "This is a very long message " * 100  # Very long message
                    }
                })

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

            event_data = {
                "event_type": "send_message",
                "data": {
                    "conversation_id": "T12345/C123456789",
                    "text": "Message with attachments",
                    "attachments": [{
                        "file_name": "file1.txt",
                        "content": "dGVzdAo="
                    }]
                }
            }
            response = await processor.process_event(event_data)

            assert response["request_completed"] is True
            assert response["message_ids"] == ["1662031200.123456"]
            processor.uploader.upload_attachments.assert_called_once()

        @pytest.mark.asyncio
        async def test_handle_send_message_missing_fields(self, processor):
            """Test handling missing fields in send message request"""
            # Missing 'text' field
            response = await processor.process_event({
                "event_type": "send_message",
                "data": {"conversation_id": "T12345/C123456789"}
            })
            assert response["request_completed"] is False

            # Missing 'conversation_id' field
            response = await processor.process_event({
                "event_type": "send_message",
                "data": {"text": "Hello, world!"}
            })
            assert response["request_completed"] is False

    class TestEditMessage:
        """Tests for the edit_message method"""

        @pytest.mark.asyncio
        async def test_edit_message_success(self, processor, slack_client_mock):
            """Test successfully editing a message"""
            slack_client_mock.chat_update.return_value = {"ok": True}
            response = await processor.process_event({
                "event_type": "edit_message",
                "data": {
                    "conversation_id": "T12345/C123456789",
                    "message_id": "1662031200.123456",
                    "text": "Updated text"
                }
            })

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
            response = await processor.process_event({
                "event_type": "edit_message",
                "data": {
                    "conversation_id": "T12345/C123456789",
                    "message_id": "1662031200.123456"
                }
            })
            assert response["request_completed"] is False

            # Missing 'message_id' field
            response = await processor.process_event({
                "event_type": "edit_message",
                "data": {
                    "conversation_id": "T12345/C123456789",
                    "text": "Updated text"
                }
            })
            assert response["request_completed"] is False

            # Missing 'conversation_id' field
            response = await processor.process_event({
                "event_type": "edit_message",
                "data": {
                    "message_id": "1662031200.123456",
                    "text": "Updated text"
                }
            })
            assert response["request_completed"] is False

    class TestDeleteMessage:
        """Tests for the delete_message method"""

        @pytest.mark.asyncio
        @pytest.mark.filterwarnings("ignore::RuntimeWarning")
        async def test_delete_message_success(self, processor, slack_client_mock):
            """Test successfully deleting a message"""
            slack_client_mock.chat_delete.return_value = {"ok": True}
            response = await processor.process_event({
                "event_type": "delete_message",
                "data": {
                    "conversation_id": "T12345/C123456789",
                    "message_id": "1662031200.123456"
                }
            })

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
            response = await processor.process_event({
                "event_type": "delete_message",
                "data": {"conversation_id": "T12345/C123456789"}
            })
            assert response["request_completed"] is False

            # Missing 'conversation_id' field
            response = await processor.process_event({
                "event_type": "delete_message",
                "data": {"message_id": "1662031200.123456"}
            })
            assert response["request_completed"] is False

    class TestReactions:
        """Tests for the reaction-related methods"""

        @pytest.mark.asyncio
        async def test_add_reaction_success(self, processor, slack_client_mock):
            """Test successfully adding a reaction"""
            slack_client_mock.reactions_add.return_value = {"ok": True}

            with patch.object(EmojiConverter, "standard_to_platform_specific", return_value="+1"):
                response = await processor.process_event({
                    "event_type": "add_reaction",
                    "data": {
                        "conversation_id": "T12345/C123456789",
                        "message_id": "1662031200.123456",
                        "emoji": "thumbs_up"
                    }
                })

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

            with patch.object(EmojiConverter, "standard_to_platform_specific", return_value="+1"):
                response = await processor.process_event({
                    "event_type": "remove_reaction",
                    "data": {
                        "conversation_id": "T12345/C123456789",
                        "message_id": "1662031200.123456",
                        "emoji": "thumbs_up"
                    }
                })

                assert response["request_completed"] is True
                processor.rate_limiter.limit_request.assert_called_once_with(
                    "remove_reaction", "T12345/C123456789"
                )
                slack_client_mock.reactions_remove.assert_called_once_with(
                    channel="C123456789",
                    timestamp="1662031200.123456",
                    name="+1"  # Using mock converter's behavior
                )

    class TestPinStatusUpdate:
        """Tests for the pin/unpin message methods"""

        @pytest.mark.asyncio
        async def test_pin_message_success(self, processor, slack_client_mock):
            """Test successfully pinning a message"""
            slack_client_mock.pins_add.return_value = {"ok": True}

            response = await processor.process_event({
                "event_type": "pin_message",
                "data": {
                    "conversation_id": "T12345/C123456789",
                    "message_id": "1662031200.123456"
                }
            })

            assert response["request_completed"] is True
            processor.rate_limiter.limit_request.assert_called_once_with(
                "pin_message", "T12345/C123456789"
            )
            slack_client_mock.pins_add.assert_called_once_with(
                channel="C123456789",
                timestamp="1662031200.123456"
            )

        @pytest.mark.asyncio
        async def test_pin_message_missing_fields(self, processor):
            """Test handling missing fields in pin message request"""
            # Missing 'message_id' field
            response = await processor.process_event({
                "event_type": "pin_message",
                "data": {"conversation_id": "T12345/C123456789"}
            })
            assert response["request_completed"] is False

            # Missing 'conversation_id' field
            response = await processor.process_event({
                "event_type": "pin_message",
                "data": {"message_id": "1662031200.123456"}
            })
            assert response["request_completed"] is False

        @pytest.mark.asyncio
        async def test_unpin_message_success(self, processor, slack_client_mock):
            """Test successfully unpinning a message"""
            slack_client_mock.pins_remove.return_value = {"ok": True}

            response = await processor.process_event({
                "event_type": "unpin_message",
                "data": {
                    "conversation_id": "T12345/C123456789",
                    "message_id": "1662031200.123456"
                }
            })

            assert response["request_completed"] is True
            processor.rate_limiter.limit_request.assert_called_once_with(
                "unpin_message", "T12345/C123456789"
            )
            slack_client_mock.pins_remove.assert_called_once_with(
                channel="C123456789",
                timestamp="1662031200.123456"
            )

        @pytest.mark.asyncio
        async def test_unpin_message_missing_fields(self, processor):
            """Test handling missing fields in unpin message request"""
            # Missing 'message_id' field
            response = await processor.process_event({
                "event_type": "unpin_message",
                "data": {"conversation_id": "T12345/C123456789"}
            })
            assert response["request_completed"] is False

            # Missing 'conversation_id' field
            response = await processor.process_event({
                "event_type": "unpin_message",
                "data": {"message_id": "1662031200.123456"}
            })
            assert response["request_completed"] is False

    class TestFetchHistory:
        """Tests for the fetch_history method"""

        @pytest.mark.asyncio
        @pytest.mark.filterwarnings("ignore::RuntimeWarning")
        async def test_fetch_history_before(self, processor):
            """Test fetching history with 'before' parameter"""
            with patch.object(HistoryFetcher, "fetch", return_value=[{"message": "test"}]):
                response = await processor.process_event({
                    "event_type": "fetch_history",
                    "data": {
                        "conversation_id": "T12345/C123456789",
                        "before": 1662031200000,  # millisecond timestamp
                        "limit": 10
                    }
                })
                assert response["request_completed"] is True

        @pytest.mark.asyncio
        @pytest.mark.filterwarnings("ignore::RuntimeWarning")
        async def test_fetch_history_after(self, processor):
            """Test fetching history with 'after' parameter"""
            with patch.object(HistoryFetcher, "fetch", return_value=[{"message": "test"}]):
                response = await processor.process_event({
                    "event_type": "fetch_history",
                    "data": {
                        "conversation_id": "T12345/C123456789",
                        "after": 1662031200000,  # millisecond timestamp
                        "limit": 10
                    }
                })

                assert response["request_completed"] is True

        @pytest.mark.asyncio
        async def test_fetch_history_missing_parameters(self, processor):
            """Test fetching history with missing before/after parameters"""
            response = await processor.process_event({
                "event_type": "fetch_history",
                "data": {
                    "conversation_id": "T12345/C123456789",
                    "limit": 10
                }
            })

            assert response["request_completed"] is False

        @pytest.mark.asyncio
        async def test_handle_fetch_history_missing_conversation_id(self, processor):
            """Test handling missing conversation_id in fetch history request"""
            response = await processor.process_event({
                "event_type": "fetch_history",
                "data": {
                    "before": 1662031200000,
                    "limit": 10
                }
            })

            assert response["request_completed"] is False
