import aiohttp
import asyncio
import discord
import pytest

from unittest.mock import AsyncMock, MagicMock, patch
from adapters.discord_webhook_adapter.adapter.adapter import Adapter
from adapters.discord_webhook_adapter.adapter.attachment_loaders.uploader import Uploader
from adapters.discord_webhook_adapter.adapter.conversation.data_classes import ConversationInfo
from adapters.discord_webhook_adapter.adapter.event_processors.history_fetcher import HistoryFetcher
from adapters.discord_webhook_adapter.adapter.event_processors.outgoing_event_processor import OutgoingEventProcessor

class TestSocketIOToDiscordWebhookFlowIntegration:
    """Integration tests for socket.io to Discord webhook flow"""

    # =============== FIXTURES ===============

    @pytest.fixture
    def socketio_mock(self):
        """Create a mocked Socket.IO server"""
        socketio = MagicMock()
        socketio.emit_event = MagicMock()
        return socketio

    @pytest.fixture
    def discord_bot_mock(self):
        """Create a mocked Discord bot"""
        bot = AsyncMock()
        bot.user = MagicMock()
        bot.user.id = 12345678
        bot.user.name = "Test Bot"
        return bot

    @pytest.fixture
    def session_mock(self):
        """Create a mocked aiohttp ClientSession"""
        session = AsyncMock()

        post_response = AsyncMock()
        post_response.status = 200
        post_response.json = AsyncMock(return_value={"id": "111222333"})
        session.post = AsyncMock(return_value=post_response)

        patch_response = AsyncMock()
        patch_response.status = 200
        patch_response.json = AsyncMock(return_value={"id": "111222333"})
        session.patch = AsyncMock(return_value=patch_response)

        delete_response = AsyncMock()
        delete_response.status = 204
        delete_response.text = AsyncMock(return_value="")
        session.delete = AsyncMock(return_value=delete_response)

        get_response = AsyncMock()
        get_response.status = 200
        get_response.json = AsyncMock(return_value={"url": "wss://gateway.discord.gg"})
        session.get = AsyncMock(return_value=get_response)

        return session

    @pytest.fixture
    def discord_webhook_client_mock(self, discord_bot_mock, session_mock):
        """Create a mocked Discord webhook client"""
        client = MagicMock()
        client.bot = discord_bot_mock
        client.session = session_mock
        client.running = True

        client.webhooks = {
            "987654321/123456789": {
                "url": "https://discord.com/api/webhooks/123456789/token",
                "name": "Test Webhook",
                "bot_token": "123456789"
            }
        }

        client.get_or_create_webhook = AsyncMock(return_value={
            "url": "https://discord.com/api/webhooks/123456789/token",
            "name": "Test Webhook",
            "bot_token": "123456789"
        })

        return client

    @pytest.fixture
    def uploader_mock(self):
        """Create a mocked Uploader"""
        uploader_mock = MagicMock(spec=Uploader)
        uploader_mock.upload_attachment = MagicMock(return_value=[])
        uploader_mock.clean_up_uploaded_files = MagicMock()
        return uploader_mock

    @pytest.fixture
    def rate_limiter_mock(self):
        """Create a mock rate limiter"""
        rate_limiter = AsyncMock()
        rate_limiter.limit_request = AsyncMock(return_value=None)
        rate_limiter.get_wait_time = AsyncMock(return_value=0)
        return rate_limiter

    @pytest.fixture
    def adapter(self,
                patch_config,
                socketio_mock,
                discord_webhook_client_mock,
                uploader_mock,
                rate_limiter_mock):
        """Create a Discord webhook adapter with mocked dependencies"""
        adapter = Adapter(patch_config, socketio_mock)
        adapter.client = discord_webhook_client_mock

        adapter.outgoing_events_processor = OutgoingEventProcessor(
            patch_config, discord_webhook_client_mock, adapter.conversation_manager
        )
        adapter.outgoing_events_processor.uploader = uploader_mock
        adapter.outgoing_events_processor.rate_limiter = rate_limiter_mock
        adapter.outgoing_events_processor.session = discord_webhook_client_mock.session

        return adapter

    @pytest.fixture
    def setup_channel_conversation(self, adapter):
        """Setup a test channel conversation"""
        def _setup():
            conversation = ConversationInfo(
                conversation_id="987654321/123456789"
            )
            adapter.conversation_manager.conversations["987654321/123456789"] = conversation
            return conversation
        return _setup

    # =============== TEST METHODS ===============

    @pytest.mark.asyncio
    async def test_send_message_flow(self, adapter):
        """Test sending a simple message"""
        assert "987654321/123456789" not in adapter.conversation_manager.conversations
        result = await adapter.process_outgoing_event({
            "event_type": "send_message",
            "data": {
                "conversation_id": "987654321/123456789",
                "text": "Hello, webhook world!"
            }
        })
        assert result["request_completed"] is True
        assert result["message_ids"] == ["111222333"]

        adapter.client.get_or_create_webhook.assert_called_with("987654321/123456789")
        adapter.outgoing_events_processor.rate_limiter.limit_request.assert_called()

        assert "987654321/123456789" in adapter.conversation_manager.conversations
        assert adapter.conversation_manager.conversations["987654321/123456789"].message_count == 1

    @pytest.mark.asyncio
    async def test_edit_message_flow(self,
                                     adapter,
                                     setup_channel_conversation,
                                     session_mock):
        """Test editing a message"""
        setup_channel_conversation()

        result = await adapter.process_outgoing_event({
            "event_type": "edit_message",
            "data": {
                "conversation_id": "987654321/123456789",
                "message_id": "111222333",
                "text": "Edited message content"
            }
        })
        assert result["request_completed"] is True

        adapter.outgoing_events_processor.rate_limiter.limit_request.assert_called_with(
            "edit_message", "https://discord.com/api/webhooks/123456789/token"
        )
        session_mock.patch.assert_called_with(
            "https://discord.com/api/webhooks/123456789/token/messages/111222333",
            json={"content": "Edited message content"}
        )

    @pytest.mark.asyncio
    async def test_delete_message_flow(self,
                                       adapter,
                                       setup_channel_conversation,
                                       session_mock):
        """Test deleting a message"""
        setup_channel_conversation()

        result = await adapter.process_outgoing_event({
            "event_type": "delete_message",
            "data": {
                "conversation_id": "987654321/123456789",
                "message_id": "111222333"
            }
        })
        assert result["request_completed"] is True

        adapter.outgoing_events_processor.rate_limiter.limit_request.assert_called_with(
            "delete_message", "https://discord.com/api/webhooks/123456789/token"
        )
        session_mock.delete.assert_called_with(
            "https://discord.com/api/webhooks/123456789/token/messages/111222333"
        )
        assert adapter.conversation_manager.conversations["987654321/123456789"].message_count == 0

    @pytest.mark.asyncio
    @pytest.mark.filterwarnings("ignore::RuntimeWarning")
    async def test_fetch_history_flow(self,
                                      adapter,
                                      setup_channel_conversation,
                                      discord_webhook_client_mock):
        """Test fetching message history"""
        setup_channel_conversation()

        history_messages = [
            {
                "message_id": "111222333",
                "conversation_id": "987654321/123456789",
                "sender": {
                    "user_id": "444555666",
                    "display_name": "Test User"
                },
                "text": "First message",
                "thread_id": None,
                "timestamp": 1627984000000,
                "attachments": []
            },
            {
                "message_id": "222333444",
                "conversation_id": "987654321/123456789",
                "sender": {
                    "user_id": "444555666",
                    "display_name": "Test User"
                },
                "text": "Second message",
                "thread_id": None,
                "timestamp": 1627984100000,
                "attachments": []
            }
        ]

        with patch.object(HistoryFetcher, "fetch") as mock_fetch:
            mock_fetch.return_value = history_messages
            discord_webhook_client_mock.get_client_bot = AsyncMock(
                return_value=discord_webhook_client_mock
            )

            result = await adapter.process_outgoing_event({
                "event_type": "fetch_history",
                "data": {
                    "conversation_id": "987654321/123456789",
                    "before": 1627985000000,  # Some time after the messages
                    "limit": 10
                }
            })

            assert result["request_completed"] is True
            assert "history" in result
            assert len(result["history"]) == 2
            assert result["history"][0]["message_id"] == "111222333"
            assert result["history"][1]["message_id"] == "222333444"
