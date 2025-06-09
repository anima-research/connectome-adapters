import asyncio
import os
import pytest

from unittest.mock import AsyncMock, MagicMock, patch
from src.adapters.slack_adapter.adapter import Adapter

class TestAdapter:
    """Tests for the Slack Adapter class"""

    @pytest.fixture
    def socketio_server_mock(self):
        """Create a mocked Socket.IO server"""
        server = AsyncMock()
        server.emit_event = AsyncMock()
        return server

    @pytest.fixture
    def slack_client_mock(self):
        """Create a mocked Client"""
        client = AsyncMock()
        client.connect = AsyncMock(return_value=True)
        client.disconnect = AsyncMock()

        # Mock the web client
        web_client = AsyncMock()
        web_client.auth_test = AsyncMock(return_value={
            "ok": True,
            "bot_id": "B12345",
            "user": "bot_user",
            "team": "T12345"
        })
        client.web_client = web_client

        return client

    @pytest.fixture
    def adapter(self, socketio_server_mock, slack_config):
        """Create a Slack Adapter with mocked dependencies"""
        manager_mock = MagicMock()
        manager_mock.message_cache = MagicMock()
        manager_mock.attachment_cache = MagicMock()

        with patch("os.path.exists", return_value=False):
            with patch("os.makedirs"):
                with patch("os.listdir", return_value=[]):
                    adapter = Adapter(slack_config, socketio_server_mock)
                    adapter.conversation_manager = manager_mock
                    yield adapter

    @pytest.fixture
    def events_processor_mock(self):
        """Create a mocked events processor"""
        def _create(return_value):
            processor = AsyncMock()
            processor.process_event = AsyncMock(return_value=return_value)
            return processor
        return _create

    @pytest.fixture
    def file_processor_mock(self):
        """Create a mocked file processor"""
        processor = AsyncMock()
        processor.schedule_file_processing = AsyncMock()
        return processor

    class TestMonitorConnection:
        """Tests for the connection monitoring"""

        @pytest.mark.asyncio
        async def test_monitor_connection_success(self, adapter, slack_client_mock):
            """Test successful connection check"""
            adapter.running = True
            adapter.initialized = True
            adapter.client = slack_client_mock

            with patch("asyncio.sleep", side_effect=[None, asyncio.CancelledError()]), \
                 patch.object(adapter, "_connection_exists", return_value=True), \
                 patch.object(adapter, "_emit_event"):

                try:
                    await adapter._monitor_connection()
                except asyncio.CancelledError:
                    pass

                adapter._emit_event.assert_called_once_with("connect")

        @pytest.mark.asyncio
        async def test_monitor_connection_failure(self, adapter, slack_client_mock):
            """Test connection check failure"""
            adapter.running = True
            adapter.initialized = True
            adapter.client = slack_client_mock

            with patch("asyncio.sleep", side_effect=[None, asyncio.CancelledError()]), \
                 patch.object(adapter, "_connection_exists", side_effect=Exception("Connection failed")), \
                 patch.object(adapter, "_emit_event"):

                try:
                    await adapter._monitor_connection()
                except asyncio.CancelledError:
                    pass

                adapter._emit_event.assert_called_once_with("disconnect")

        @pytest.mark.asyncio
        async def test_connection_exists(self, adapter, slack_client_mock):
            """Test the connection check method"""
            adapter.client = slack_client_mock
            result = await adapter._connection_exists()

            slack_client_mock.web_client.auth_test.assert_called_once()
            assert result == slack_client_mock.web_client.auth_test.return_value

    class TestEventProcessing:
        """Tests for event processing"""

        @pytest.mark.asyncio
        async def test_process_standard_event(self, adapter, events_processor_mock):
            """Test processing standard Slack events"""
            adapter.incoming_events_processor = events_processor_mock([{"test": "event"}])
            test_event = {"type": "message", "event": {"text": "Hello"}}

            await adapter.process_incoming_event(test_event)

            adapter.incoming_events_processor.process_event.assert_called_once_with(test_event)
            adapter.socketio_server.emit_event.assert_called_once_with("bot_request", {"test": "event"})

        @pytest.mark.asyncio
        async def test_process_file_share_event(self, adapter, file_processor_mock):
            """Test processing file share events"""
            adapter.file_processor = file_processor_mock
            test_event = {"type": "file_share", "event": {"files": [{"id": "F12345"}]}}

            await adapter.process_incoming_event(test_event)

            adapter.file_processor.schedule_file_processing.assert_called_once_with(test_event["event"])

        @pytest.mark.asyncio
        async def test_process_outgoing_event(self, adapter, events_processor_mock):
            """Test processing outgoing events"""
            adapter.outgoing_events_processor = events_processor_mock({"request_completed": True})
            adapter.client = MagicMock()
            test_data = {
                "event_type": "send_message",
                "data": {
                    "conversation_id": "C12345",
                    "text": "Hello, world!"
                }
            }
            response = await adapter.process_outgoing_event(test_data)

            assert response["request_completed"] is True
            adapter.outgoing_events_processor.process_event.assert_called_once_with(test_data)

        @pytest.mark.asyncio
        async def test_process_outgoing_event_not_connected(self, adapter):
            """Test processing outgoing events when not connected"""
            adapter.client = None
            response = await adapter.process_outgoing_event({
                "event_type": "send_message",
                "data": {
                    "conversation_id": "C12345",
                    "text": "Hello, world!"
                }
            })

            assert response["request_completed"] is False
