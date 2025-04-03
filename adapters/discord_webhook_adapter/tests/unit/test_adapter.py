import pytest
import asyncio
import discord
import aiohttp
from unittest.mock import AsyncMock, MagicMock, patch

from adapters.discord_webhook_adapter.adapter.adapter import Adapter
from adapters.discord_webhook_adapter.adapter.conversation.manager import Manager
from adapters.discord_webhook_adapter.adapter.discord_webhook_client import DiscordWebhookClient
from adapters.discord_webhook_adapter.adapter.event_processors.outgoing_event_processor import OutgoingEventProcessor

class TestWebhookAdapter:
    """Tests for the Discord Webhook Adapter class"""

    @pytest.fixture
    def socketio_server_mock(self):
        """Create a mocked Socket.IO server"""
        server = AsyncMock()
        server.emit_event = AsyncMock()
        return server

    @pytest.fixture
    def discord_webhook_client_mock(self):
        """Create a mocked DiscordWebhookClient"""
        client = AsyncMock()
        client.connect = AsyncMock(return_value=True)
        client.disconnect = AsyncMock()
        client.running = True
        client.webhooks = {
            "987654321/123456789": {
                "url": "https://discord.com/api/webhooks/123456789/token",
                "name": "Test Bot"
            }
        }

        # Mock the session
        session_mock = AsyncMock()
        response_mock = AsyncMock()
        response_mock.status = 200
        response_mock.json = AsyncMock(return_value={"url": "wss://gateway.discord.gg"})
        session_mock.get = AsyncMock(return_value=response_mock)
        client.session = session_mock

        # Mock Discord bot
        bot = AsyncMock()
        bot.user = MagicMock()
        bot.user.id = 123456789
        bot.user.name = "Test Bot"
        client.bot = bot

        return client

    @pytest.fixture
    def manager_mock(self):
        """Create a mocked Manager"""
        return MagicMock()

    @pytest.fixture
    def processor_mock(self):
        """Create a mocked OutgoingEventProcessor"""
        processor = AsyncMock()
        processor.process_event = AsyncMock(
            return_value={"request_completed": True}
        )
        return processor

    @pytest.fixture
    def adapter(self, socketio_server_mock, patch_config):
        """Create a Discord Webhook Adapter with mocked dependencies"""
        with patch.object(Manager, "__new__", return_value=MagicMock()):
            yield Adapter(patch_config, socketio_server_mock)

    class TestConnectionMonitoring:
        """Tests for connection monitoring"""

        @pytest.mark.asyncio
        async def test_monitor_connection_success(self, adapter, discord_webhook_client_mock):
            """Test successful connection monitoring"""
            adapter.running = True
            adapter.initialized = True
            adapter.client = discord_webhook_client_mock

            with patch.object(adapter, "_connection_exists", return_value={"url": "wss://gateway.discord.gg"}):
                with patch("asyncio.sleep", side_effect=[None, asyncio.CancelledError()]):
                    try:
                        await adapter._monitor_connection()
                    except asyncio.CancelledError:
                        pass

                    adapter.socketio_server.emit_event.assert_called_once_with(
                        "connect", {"adapter_type": adapter.adapter_type}
                    )

        @pytest.mark.asyncio
        async def test_monitor_connection_failure(self, adapter, discord_webhook_client_mock):
            """Test connection monitoring failure"""
            adapter.running = True
            adapter.initialized = True
            adapter.client = discord_webhook_client_mock

            with patch.object(adapter, "_connection_exists", return_value=None):
                with patch("asyncio.sleep", side_effect=[None, asyncio.CancelledError()]):
                    try:
                        await adapter._monitor_connection()
                    except asyncio.CancelledError:
                        pass

                    adapter.socketio_server.emit_event.assert_called_once_with(
                        "disconnect", {"adapter_type": adapter.adapter_type}
                    )

    class TestEventProcessing:
        """Tests for event processing"""

        @pytest.mark.asyncio
        async def test_process_outgoing_event_success(self, adapter, processor_mock):
            """Test successful processing of outgoing events"""
            adapter.outgoing_events_processor = processor_mock
            adapter.client = MagicMock()
            adapter.client.running = True

            test_data = {"conversation_id": "987654321/123456789", "text": "Test message"}
            result = await adapter.process_outgoing_event("send_message", test_data)
            assert result["request_completed"] is True

            processor_mock.process_event.assert_called_once_with("send_message", test_data)

        @pytest.mark.asyncio
        async def test_process_outgoing_event_discord_not_connected(self, adapter):
            """Test processing outgoing events when not connected"""
            adapter.client = None

            test_data = {"conversation_id": "987654321/123456789", "text": "Test message"}
            result = await adapter.process_outgoing_event("send_message", test_data)
            assert result["request_completed"] is False
