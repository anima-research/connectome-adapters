import pytest
import asyncio

from unittest.mock import AsyncMock, MagicMock, patch
from src.adapters.zulip_adapter.adapter import Adapter

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
    def adapter(self, socketio_server_mock, rate_limiter_mock, zulip_config):
        """Create a ZulipAdapter with mocked dependencies"""
        manager_mock = MagicMock()
        attachment_cache_mock = MagicMock()
        message_cache_mock = MagicMock()

        manager_mock.message_cache = message_cache_mock
        manager_mock.attachment_cache = attachment_cache_mock

        with patch("os.path.exists", return_value=False):
            with patch("os.makedirs"):
                with patch("os.listdir", return_value=[]):
                    adapter = Adapter(zulip_config, socketio_server_mock)
                    adapter.manager = manager_mock
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
            connection_check_calls = 0

            async def mock_connection_exists():
                nonlocal connection_check_calls
                connection_check_calls += 1
                if connection_check_calls > 5:  # Simulate max attempts
                    raise RuntimeError("Connection check failed")
                return False

            adapter._connection_exists = mock_connection_exists
            adapter._reconnect_with_client = AsyncMock()

            sleep_calls = 0
            async def mock_sleep(duration):
                nonlocal sleep_calls
                sleep_calls += 1
                if sleep_calls > 7:
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
            test_data = {"event_type": "send_message", "data": {"test": "socket_data"}}

            response = await adapter.process_outgoing_event(test_data)
            assert response["request_completed"] is True
            adapter.outgoing_events_processor.process_event.assert_called_once_with(test_data)

        @pytest.mark.asyncio
        async def test_process_socket_io_event_not_connected(self, adapter):
            """Test processing Socket.IO events when not connected"""
            adapter.client = None

            response = await adapter.process_outgoing_event({"event_type": "send_message", "data": {"test": "socket_data"}})
            assert response["request_completed"] is False
