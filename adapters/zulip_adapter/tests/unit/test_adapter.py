import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from adapters.zulip_adapter.adapter.adapter import Adapter
from adapters.zulip_adapter.adapter.conversation.manager import Manager
from core.cache.attachment_cache import AttachmentCache
from core.cache.message_cache import MessageCache

class TestAdapter:
    """Tests for the Adapter class"""

    @pytest.fixture
    def socketio_server_mock(self):
        """Create a mocked Socket.IO server"""
        server = AsyncMock()
        server.emit_event = AsyncMock()
        return server

    @pytest.fixture
    def zulip_client_mock(self):
        """Create a mocked ZulipClient"""
        client = AsyncMock()
        client.connect = AsyncMock()
        client.disconnect = AsyncMock()
        client.start_polling = AsyncMock()
        client.client = AsyncMock()
        client.client.get_profile = MagicMock(return_value={
            "result": "success",
            "full_name": "Test Bot",
            "email": "test@example.com"
        })
        client.running = True
        return client

    @pytest.fixture
    def rate_limiter_mock(self):
        """Create a mock rate limiter"""
        rate_limiter = AsyncMock()
        rate_limiter.limit_request = AsyncMock(return_value=None)
        rate_limiter.get_wait_time = AsyncMock(return_value=0)
        return rate_limiter

    @pytest.fixture
    def adapter(self, socketio_server_mock, rate_limiter_mock, patch_config):
        """Create a ZulipAdapter with mocked dependencies"""
        manager_mock = MagicMock()
        attachment_cache_mock = MagicMock()
        message_cache_mock = MagicMock()

        manager_mock.message_cache = message_cache_mock
        manager_mock.attachment_cache = attachment_cache_mock

        with patch.object(Manager, "__new__", return_value=manager_mock):
            with patch.object(AttachmentCache, "__new__", return_value=attachment_cache_mock):
                with patch.object(MessageCache, "__new__", return_value=message_cache_mock):
                    with patch("os.path.exists", return_value=False):
                        with patch("os.makedirs"):
                            with patch("os.listdir", return_value=[]):
                                adapter = Adapter(patch_config, socketio_server_mock)
                                adapter.rate_limiter = rate_limiter_mock
                                yield adapter

    class TestMonitorConnection:
        """Tests for the connection monitoring"""

        @pytest.mark.asyncio
        @pytest.mark.filterwarnings("ignore::RuntimeWarning")
        async def test_monitor_connection_success(self, adapter, zulip_client_mock):
            """Test successful connection check"""
            adapter.running = True
            adapter.initialized = True
            adapter.client = zulip_client_mock

            with patch("asyncio.sleep", side_effect=[None, asyncio.CancelledError()]):
                try:
                    await adapter._monitor_connection()
                except asyncio.CancelledError:
                    pass

                adapter.socketio_server.emit_event.assert_called_once_with(
                    "connect", {"adapter_type": adapter.adapter_type}
                )

        @pytest.mark.asyncio
        async def test_monitor_connection_failure(self, adapter, zulip_client_mock):
            """Test connection check failure"""
            adapter.running = True
            adapter.initialized = True
            adapter.client = zulip_client_mock
            zulip_client_mock.client.get_profile.return_value = {"result": "error"}

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
        async def test_process_zulip_event(self, adapter, events_processor_mock):
            """Test processing Zulip events"""
            adapter.incoming_events_processor = events_processor_mock([{"test": "event"}])
            test_event = {"type": "message", "data": "test_data"}

            await adapter.process_incoming_event(test_event)

            adapter.incoming_events_processor.process_event.assert_called_once_with(test_event)
            adapter.socketio_server.emit_event.assert_called_once_with("bot_request", {"test": "event"})

        @pytest.mark.asyncio
        async def test_process_socket_io_event(self, adapter, events_processor_mock):
            """Test processing Socket.IO events"""
            adapter.outgoing_events_processor = events_processor_mock({"request_completed": True})
            adapter.client = MagicMock()
            test_data = {"test": "socket_data"}

            response = await adapter.process_outgoing_event("send_message", test_data)
            assert response["request_completed"] is True
            adapter.outgoing_events_processor.process_event.assert_called_once_with("send_message", test_data)

        @pytest.mark.asyncio
        async def test_process_socket_io_event_not_connected(self, adapter):
            """Test processing Socket.IO events when not connected"""
            adapter.client = None

            response = await adapter.process_outgoing_event("send_message", {"test": "socket_data"})
            assert response["request_completed"] is False
