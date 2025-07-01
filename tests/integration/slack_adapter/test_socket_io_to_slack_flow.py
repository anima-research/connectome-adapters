import asyncio
import os
import pytest
import time

from unittest.mock import AsyncMock, MagicMock, patch
from src.adapters.slack_adapter.adapter import Adapter
from src.adapters.slack_adapter.conversation.data_classes import ConversationInfo
from src.adapters.slack_adapter.attachment_loaders.uploader import Uploader
from src.adapters.slack_adapter.event_processors.outgoing_event_processor import OutgoingEventProcessor
from src.adapters.slack_adapter.event_processors.history_fetcher import HistoryFetcher
from src.adapters.slack_adapter.event_processors.incoming_event_processor import IncomingEventProcessor
from src.core.utils.emoji_converter import EmojiConverter

class TestSocketIOToSlackFlowIntegration:
    """Integration tests for socket.io to Slack flow"""

    # =============== FIXTURES ===============

    @pytest.fixture
    def socketio_mock(self):
        """Create a mocked Socket.IO server"""
        socketio = MagicMock()
        socketio.emit_event = AsyncMock()
        return socketio

    @pytest.fixture
    def web_client_mock(self):
        """Create a mocked Slack Web API client"""
        client = AsyncMock()
        # Mock successful message post response
        client.chat_postMessage = AsyncMock(return_value={
            "ok": True,
            "ts": "1662031200.123456"
        })
        # Mock successful message update response
        client.chat_update = AsyncMock(return_value={
            "ok": True,
            "ts": "1662031200.123456",
            "text": "Edited message content"
        })
        # Mock successful message delete response
        client.chat_delete = AsyncMock(return_value={
            "ok": True
        })
        # Mock successful reaction add response
        client.reactions_add = AsyncMock(return_value={
            "ok": True
        })
        # Mock successful reaction remove response
        client.reactions_remove = AsyncMock(return_value={
            "ok": True
        })
        # Mock successful history response
        client.conversations_history = AsyncMock(return_value={
            "ok": True
        })

        return client

    @pytest.fixture
    def slack_client_mock(self, web_client_mock):
        """Create a mocked Slack client"""
        client = MagicMock()
        client.web_client = web_client_mock
        client.socket_client = MagicMock()
        client.running = True
        return client

    @pytest.fixture
    def uploader_mock(self):
        """Create a mocked Uploader"""
        uploader_mock = AsyncMock(spec=Uploader)
        uploader_mock.upload_attachments = AsyncMock(return_value=[])
        return uploader_mock

    @pytest.fixture
    def rate_limiter_mock(self):
        """Create a mock rate limiter"""
        rate_limiter = AsyncMock()
        rate_limiter.limit_request = AsyncMock(return_value=None)
        rate_limiter.get_wait_time = AsyncMock(return_value=0)
        return rate_limiter

    @pytest.fixture
    def emoji_converter_mock(self):
        """Create a mock emoji converter"""
        converter = MagicMock(spec=EmojiConverter)
        converter.standard_to_platform_specific = MagicMock(return_value="+1")
        return converter

    @pytest.fixture
    def adapter(self,
                slack_config,
                socketio_mock,
                slack_client_mock,
                uploader_mock,
                rate_limiter_mock):
        """Create a Slack adapter with mocked dependencies"""
        adapter = Adapter(slack_config, socketio_mock)
        adapter.client = slack_client_mock
        adapter.rate_limiter = rate_limiter_mock
        adapter.connected = True
        adapter.initialized = True

        adapter.outgoing_events_processor = OutgoingEventProcessor(
            slack_config, slack_client_mock.web_client, adapter.conversation_manager
        )
        adapter.outgoing_events_processor.uploader = uploader_mock
        adapter.outgoing_events_processor.rate_limiter = rate_limiter_mock

        adapter.incoming_events_processor = IncomingEventProcessor(
            slack_config, slack_client_mock.web_client, adapter.conversation_manager
        )
        adapter.incoming_events_processor.rate_limiter = rate_limiter_mock

        return adapter

    @pytest.fixture
    def standard_conversation_id(self):
        """Create a mock standard conversation ID"""
        return "slack_F0OIohoDYwVnEyYccO7j"

    @pytest.fixture
    def setup_conversation(self, adapter, standard_conversation_id):
        """Setup a test conversation with a user"""
        def _setup():
            adapter.conversation_manager.conversations[standard_conversation_id] = ConversationInfo(
                platform_conversation_id="T123/C456",
                conversation_id=standard_conversation_id,
                conversation_type="channel"
            )
            return adapter.conversation_manager.conversations[standard_conversation_id]
        return _setup

    # =============== TEST METHODS ===============

    @pytest.mark.asyncio
    async def test_send_message_flow(self, adapter, setup_conversation, standard_conversation_id):
        """Test sending a simple message to Slack"""
        setup_conversation()

        response = await adapter.process_outgoing_event({
            "event_type": "send_message",
            "data": {
                "conversation_id": standard_conversation_id,
                "text": "Hello, Slack world!"
            }
        })
        assert response["request_completed"] is True
        assert "message_ids" in response
        assert len(response["message_ids"]) == 1
        assert response["message_ids"][0] == "1662031200.123456"

        # Verify that the Slack API was called correctly
        adapter.client.web_client.chat_postMessage.assert_called_once_with(
            channel="C456",
            text="Hello, Slack world!",
            unfurl_links=False,
            unfurl_media=False
        )

    @pytest.mark.asyncio
    async def test_send_message_with_attachment_flow(self,
                                                     adapter,
                                                     uploader_mock,
                                                     setup_conversation,
                                                     standard_conversation_id):
        """Test sending a message with an attachment to Slack"""
        setup_conversation()

        uploader_mock.upload_attachments.return_value = []
        response = await adapter.process_outgoing_event({
            "event_type": "send_message",
            "data": {
                "conversation_id": standard_conversation_id,
                "text": "See attachment",
                "attachments": [
                    {
                        "file_name": "test.txt",
                        "content": "dGVzdAo="
                    }
                ]
            }
        })
        assert response["request_completed"] is True

        adapter.client.web_client.chat_postMessage.assert_called_once()
        uploader_mock.upload_attachments.assert_called_once()

    @pytest.mark.asyncio
    async def test_edit_message_flow(self, adapter, setup_conversation, standard_conversation_id):
        """Test the complete flow from socket.io edit_message to Slack API call"""
        setup_conversation()

        response = await adapter.process_outgoing_event({
            "event_type": "edit_message",
            "data": {
                "conversation_id": standard_conversation_id,
                "message_id": "1662031200.123456",
                "text": "Edited message content"
            }
        })
        assert response["request_completed"] is True

        # Verify that the Slack API was called correctly
        adapter.client.web_client.chat_update.assert_called_once_with(
            channel="C456",
            ts="1662031200.123456",
            text="Edited message content"
        )

    @pytest.mark.asyncio
    async def test_delete_message_flow(self, adapter, setup_conversation, standard_conversation_id):
        """Test the complete flow from socket.io delete_message to Slack API call"""
        setup_conversation()

        response = await adapter.process_outgoing_event({
            "event_type": "delete_message",
            "data": {
                "conversation_id": standard_conversation_id,
                "message_id": "1662031200.123456"
            }
        })
        assert response["request_completed"] is True

        # Verify that the Slack API was called correctly
        adapter.client.web_client.chat_delete.assert_called_once_with(
            channel="C456",
            ts="1662031200.123456"
        )

    @pytest.mark.asyncio
    async def test_add_reaction_flow(self,
                                     adapter,
                                     emoji_converter_mock,
                                     setup_conversation,
                                     standard_conversation_id):
        """Test the complete flow from socket.io add_reaction to Slack API call"""
        setup_conversation()

        with patch(
            "src.core.utils.emoji_converter.EmojiConverter.get_instance",
            return_value=emoji_converter_mock
        ):
            response = await adapter.process_outgoing_event({
                "event_type": "add_reaction",
                "data": {
                    "conversation_id": standard_conversation_id,
                    "message_id": "1662031200.123456",
                    "emoji": "thumbs_up"
                }
            })
            assert response["request_completed"] is True

            emoji_converter_mock.standard_to_platform_specific.assert_called_once_with("thumbs_up")
            adapter.client.web_client.reactions_add.assert_called_once_with(
                channel="C456",
                timestamp="1662031200.123456",
                name="+1"  # From emoji converter mock
            )

    @pytest.mark.asyncio
    async def test_remove_reaction_flow(self,
                                        adapter,
                                        emoji_converter_mock,
                                        setup_conversation,
                                        standard_conversation_id):
        """Test the complete flow from socket.io remove_reaction to Slack API call"""
        setup_conversation()

        with patch(
            "src.core.utils.emoji_converter.EmojiConverter.get_instance",
            return_value=emoji_converter_mock
        ):
            response = await adapter.process_outgoing_event({
                "event_type": "remove_reaction",
                "data": {
                    "conversation_id": standard_conversation_id,
                    "message_id": "1662031200.123456",
                    "emoji": "thumbs_up"
                }
            })
            assert response["request_completed"] is True

            emoji_converter_mock.standard_to_platform_specific.assert_called_once_with("thumbs_up")
            adapter.client.web_client.reactions_remove.assert_called_once_with(
                channel="C456",
                timestamp="1662031200.123456",
                name="+1"  # From emoji converter mock
            )

    @pytest.mark.asyncio
    async def test_fetch_history_flow(self, adapter, setup_conversation, standard_conversation_id):
        """Test the complete flow from socket.io fetch_history to HistoryFetcher"""
        setup_conversation()

        mock_history = [
            {
                "message_id": "1662031200.123456",
                "conversation_id": standard_conversation_id,
                "sender": {"user_id": "U12345678", "display_name": "Test User"},
                "text": "Test message",
                "timestamp": 1662031200123
            }
        ]

        with patch.object(HistoryFetcher, "fetch", return_value=mock_history):
            response = await adapter.process_outgoing_event({
                "event_type": "fetch_history",
                "data": {
                    "conversation_id": standard_conversation_id,
                    "before": int(time.time()),
                    "limit": 10
                }
            })
            assert response["request_completed"] is True

    @pytest.mark.asyncio
    async def test_pin_message_flow(self, adapter, setup_conversation, standard_conversation_id):
        """Test the complete flow from socket.io pin_message to Slack API call"""
        setup_conversation()
        adapter.client.web_client.pins_add = AsyncMock(return_value={"ok": True})

        response = await adapter.process_outgoing_event({
            "event_type": "pin_message",
            "data": {
                "conversation_id": standard_conversation_id,
                "message_id": "1662031200.123456"
            }
        })
        assert response["request_completed"] is True

        adapter.client.web_client.pins_add.assert_called_once_with(
            channel="C456",
            timestamp="1662031200.123456"
        )

    @pytest.mark.asyncio
    async def test_unpin_message_flow(self, adapter, setup_conversation, standard_conversation_id):
        """Test the complete flow from socket.io unpin_message to Slack API call"""
        setup_conversation()
        adapter.client.web_client.pins_remove = AsyncMock(return_value={"ok": True})

        response = await adapter.process_outgoing_event({
            "event_type": "unpin_message",
            "data": {
                "conversation_id": standard_conversation_id,
                "message_id": "1662031200.123456"
            }
        })
        assert response["request_completed"] is True

        adapter.client.web_client.pins_remove.assert_called_once_with(
            channel="C456",
            timestamp="1662031200.123456"
        )
