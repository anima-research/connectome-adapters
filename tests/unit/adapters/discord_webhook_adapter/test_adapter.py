import pytest
import asyncio
import discord
import aiohttp
from unittest.mock import AsyncMock, MagicMock, patch

from src.adapters.discord_webhook_adapter.adapter import Adapter
from src.adapters.discord_webhook_adapter.conversation.manager import Manager
from src.adapters.discord_webhook_adapter.client import Client
from src.adapters.discord_webhook_adapter.event_processors.outgoing_event_processor import OutgoingEventProcessor

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
    def adapter(self, socketio_server_mock, discord_webhook_config):
        """Create a Discord Webhook Adapter with mocked dependencies"""
        adapter = Adapter(discord_webhook_config, socketio_server_mock)
        adapter.conversation_manager = MagicMock()
        return adapter

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
                with patch.object(adapter, "_reconnect_with_client", return_value=None):
                    max_attempts = 5
                    adapter.config.get_setting = MagicMock(
                        side_effect=lambda section, key, default=None:
                        max_attempts if key == "max_reconnect_attempts" else 0
                    )
                    sleep_calls = 0

                    async def mock_sleep(*args, **kwargs):
                        nonlocal sleep_calls
                        sleep_calls += 1
                        if sleep_calls > max_attempts + 1:  # +1 for the retry sleep
                            raise asyncio.CancelledError()

                    with patch("asyncio.sleep", side_effect=mock_sleep):
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

            test_data = {
                "event_type": "send_message",
                "data": {
                    "conversation_id": "987654321/123456789",
                    "text": "Test message"
                }
            }
            result = await adapter.process_outgoing_event(test_data)
            assert result["request_completed"] is True

            processor_mock.process_event.assert_called_once_with(test_data)

        @pytest.mark.asyncio
        async def test_process_outgoing_event_discord_not_connected(self, adapter):
            """Test processing outgoing events when not connected"""
            adapter.client = None
            test_data = {
                "event_type": "send_message",
                "data": {
                    "conversation_id": "987654321/123456789",
                    "text": "Test message"
                }
            }
            result = await adapter.process_outgoing_event(test_data)

            assert result["request_completed"] is False
