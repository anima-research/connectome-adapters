import pytest
import asyncio
import discord
from unittest.mock import AsyncMock, MagicMock, patch

from src.adapters.discord_adapter.adapter import Adapter

class TestAdapter:
    """Tests for the Discord Adapter class"""

    @pytest.fixture
    def socketio_server_mock(self):
        """Create a mocked Socket.IO server"""
        server = AsyncMock()
        server.emit_event = AsyncMock()
        return server

    @pytest.fixture
    def discord_client_mock(self):
        """Create a mocked DiscordClient"""
        client = AsyncMock()
        client.connect = AsyncMock(return_value=True)
        client.disconnect = AsyncMock()
        client.running = True

        # Mock the Discord bot
        bot = AsyncMock()
        bot.user = MagicMock()
        bot.user.id = 123456789
        bot.user.name = "Test Bot"
        bot.fetch_user = AsyncMock(return_value=bot.user)
        client.bot = bot

        return client

    @pytest.fixture
    def adapter(self, socketio_server_mock, discord_config):
        """Create a Discord Adapter with mocked dependencies"""
        manager_mock = MagicMock()
        manager_mock.message_cache = MagicMock()
        manager_mock.attachment_cache = MagicMock()

        with patch("os.path.exists", return_value=False):
            with patch("os.makedirs"):
                with patch("os.listdir", return_value=[]):
                    adapter = Adapter(discord_config, socketio_server_mock)
                    adapter.conversation_manager = manager_mock
                    return adapter

    class TestMonitorConnection:
        """Tests for the connection monitoring"""

        @pytest.mark.asyncio
        async def test_monitor_connection_success(self, adapter, discord_client_mock):
            """Test successful connection check"""
            adapter.running = True
            adapter.initialized = True
            adapter.client = discord_client_mock
            adapter.config.get_setting = MagicMock(return_value="123456789")

            with patch("asyncio.sleep", side_effect=[None, asyncio.CancelledError()]):
                try:
                    await adapter._monitor_connection()
                except asyncio.CancelledError:
                    pass

                adapter.socketio_server.emit_event.assert_called_once_with(
                    "connect", {"adapter_type": adapter.adapter_type}
                )

        @pytest.mark.asyncio
        async def test_monitor_connection_failure(self, adapter, discord_client_mock):
            """Test connection check failure"""
            adapter.running = True
            adapter.initialized = True
            adapter.client = discord_client_mock
            discord_client_mock.bot.fetch_user.side_effect = discord.NotFound(MagicMock(), "User not found")

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

        @pytest.fixture
        def events_processor_mock(self):
            """Create a mocked events processor"""
            def _create(return_value):
                processor = AsyncMock()
                processor.process_event = AsyncMock(return_value=return_value)
                return processor
            return _create

        @pytest.mark.asyncio
        async def test_process_discord_event(self, adapter, events_processor_mock):
            """Test processing Discord events"""
            adapter.incoming_events_processor = events_processor_mock([{"test": "event"}])
            test_event = {"type": "new_message", "event": MagicMock()}

            await adapter.process_incoming_event(test_event)

            adapter.incoming_events_processor.process_event.assert_called_once_with(test_event)
            adapter.socketio_server.emit_event.assert_called_once_with("bot_request", {"test": "event"})

        @pytest.mark.asyncio
        async def test_process_socket_io_event(self, adapter, events_processor_mock):
            """Test processing Socket.IO events"""
            adapter.outgoing_events_processor = events_processor_mock({"request_completed": True})
            adapter.client = MagicMock()
            adapter.client.running = True

            test_data = {
                "event_type": "send_message",
                "data": {"test": "socket_data"}
            }
            response = await adapter.process_outgoing_event(test_data)

            assert response["request_completed"] is True
            adapter.outgoing_events_processor.process_event.assert_called_once_with(test_data)

        @pytest.mark.asyncio
        async def test_process_socket_io_event_not_connected(self, adapter):
            """Test processing Socket.IO events when not connected"""
            adapter.client = None
            response = await adapter.process_outgoing_event({
                "event_type": "send_message",
                "data": {"test": "socket_data"}
            })

            assert response["request_completed"] is False
