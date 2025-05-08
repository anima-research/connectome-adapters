import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from adapters.telegram_adapter.adapter.adapter import Adapter
from adapters.telegram_adapter.adapter.conversation.manager import Manager

from core.cache.attachment_cache import AttachmentCache
from core.cache.message_cache import MessageCache

class TestAdapter:
    """Tests for the TelegramAdapter class"""

    @pytest.fixture
    def socketio_server_mock(self):
        """Create a mocked Socket.IO server"""
        server = AsyncMock()
        server.emit_event = AsyncMock()
        return server

    @pytest.fixture
    def telethon_client_mock(self):
        """Create a mocked TelethonClient"""
        client = AsyncMock()
        client.connect = AsyncMock(return_value=True)
        client.disconnect = AsyncMock()
        client.client = AsyncMock()
        client.client.get_me = AsyncMock()
        client.connected = True
        return client

    @pytest.fixture
    def incoming_event_processor_mock(self):
        """Create a mocked IncomingEventProcessor"""
        processor = AsyncMock()
        processor.process_event = AsyncMock(return_value=[{"test": "event"}])
        return processor

    @pytest.fixture
    def outgoing_event_processor_mock(self):
        """Create a mocked OutgoingEventProcessor"""
        processor = AsyncMock()
        processor.process_event = AsyncMock(return_value=True)
        return processor

    @pytest.fixture
    def conversation_manager_mock(self):
        """Create a mocked ConversationManager"""
        return MagicMock()

    @pytest.fixture
    def rate_limiter_mock(self):
        """Create a mock rate limiter"""
        rate_limiter = AsyncMock()
        rate_limiter.limit_request = AsyncMock(return_value=None)
        rate_limiter.get_wait_time = AsyncMock(return_value=0)
        return rate_limiter

    @pytest.fixture
    def adapter(self, socketio_server_mock, rate_limiter_mock, patch_config):
        """Create a Adapter with mocked dependencies"""
        conversation_manager_mock = MagicMock()
        attachment_cache_mock = MagicMock()
        message_cache_mock = MagicMock()

        conversation_manager_mock.message_cache = message_cache_mock
        conversation_manager_mock.attachment_cache = attachment_cache_mock

        with patch.object(Manager, "__new__", return_value=conversation_manager_mock):
            with patch.object(AttachmentCache, "__new__", return_value=attachment_cache_mock):
                with patch.object(MessageCache, "__new__", return_value=message_cache_mock):
                    with patch('os.path.exists', return_value=False):
                        with patch('os.makedirs'):
                            with patch('os.listdir', return_value=[]):
                                adapter = Adapter(patch_config, socketio_server_mock)
                                adapter.rate_limiter = rate_limiter_mock
                                yield adapter

    class TestMonitorConnection:
        """Tests for the connection monitoring"""

        @pytest.mark.asyncio
        @pytest.mark.filterwarnings("ignore::RuntimeWarning")
        async def test_monitor_connection_success(self, adapter, telethon_client_mock):
            """Test successful connection check"""
            adapter.running = True
            adapter.initialized = True
            adapter.client = telethon_client_mock

            sleep_mock = AsyncMock()
            sleep_mock.side_effect = [None, asyncio.CancelledError()]

            with patch("asyncio.sleep", side_effect=[None, asyncio.CancelledError()]):
                try:
                    await adapter._monitor_connection()
                except asyncio.CancelledError:
                    pass

                telethon_client_mock.client.get_me.assert_called_once()
                adapter.socketio_server.emit_event.assert_called_once_with(
                    "connect", {"adapter_type": "telegram"}
                )

        @pytest.mark.asyncio
        async def test_monitor_connection_failure(self, adapter, telethon_client_mock):
            """Test connection check failure"""
            adapter.running = True
            adapter.initialized = True
            adapter.client = telethon_client_mock
            telethon_client_mock.client.get_me.return_value = None

            with patch("asyncio.sleep", side_effect=[None, asyncio.CancelledError()]):
                try:
                    await adapter._monitor_connection()
                except asyncio.CancelledError:
                    pass

                adapter.socketio_server.emit_event.assert_called_once_with(
                    "disconnect", {"adapter_type": "telegram"}
                )

    class TestEventProcessing:
        """Tests for event processing"""

        @pytest.mark.asyncio
        async def test_process_telegram_event(self, adapter, incoming_event_processor_mock):
            """Test processing Telegram events"""
            adapter.incoming_events_processor = incoming_event_processor_mock
            test_event = {"type": "new_message", "event": {"message": "test"}}

            await adapter.process_incoming_event(test_event)

            incoming_event_processor_mock.process_event.assert_called_once_with(test_event)
            adapter.socketio_server.emit_event.assert_called_once_with("bot_request", {"test": "event"})

        @pytest.mark.asyncio
        async def test_process_socket_io_event(self, adapter, outgoing_event_processor_mock):
            """Test processing Socket.IO events"""
            adapter.outgoing_events_processor = outgoing_event_processor_mock
            adapter.client = MagicMock()

            test_data = {
                "event_type": "send_message",
                "data": {"test": "socket_data"}
            }
            result = await adapter.process_outgoing_event(test_data)

            outgoing_event_processor_mock.process_event.assert_called_once_with(test_data)
            assert result is True
