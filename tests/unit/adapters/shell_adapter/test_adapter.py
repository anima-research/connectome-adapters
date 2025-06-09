import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

from src.adapters.shell_adapter.adapter import Adapter
from src.adapters.shell_adapter.event_processor.processor import Processor
from src.adapters.shell_adapter.session.manager import Manager

class TestShellAdapter:
    """Tests for the Shell Adapter class"""

    @pytest.fixture
    def mock_config(self):
        """Create a mock config for testing"""
        config = MagicMock()
        config.get_setting.side_effect = lambda section, key: {
            ("adapter", "adapter_type"): "shell",
            ("adapter", "connection_check_interval"): 5,
            ("adapter", "workspace_directory"): "/home/user/workspace",
            ("adapter", "command_max_lifetime"): 60,
            ("adapter", "session_max_lifetime"): 120,
            ("adapter", "cpu_percent_limit"): 80,
            ("adapter", "memory_mb_limit"): 500
        }.get((section, key))
        return config

    @pytest.fixture
    def mock_socketio_server(self):
        """Create a mock Socket.IO server"""
        server = AsyncMock()
        server.emit_event = AsyncMock()
        return server

    @pytest.fixture
    def mock_session_manager(self):
        """Create a mock session manager"""
        manager = AsyncMock(spec=Manager)
        manager.start = AsyncMock()
        manager.stop = AsyncMock()
        return manager

    @pytest.fixture
    def mock_processor(self):
        """Create a mock event processor"""
        processor = AsyncMock(spec=Processor)
        processor.process_event = AsyncMock(return_value={"request_completed": True})
        return processor

    @pytest.fixture
    def adapter(self, mock_config, mock_socketio_server, mock_session_manager, mock_processor):
        """Create an adapter with mocked config and server"""
        adapter = Adapter(mock_config, mock_socketio_server)
        adapter.session_manager = mock_session_manager
        adapter.outgoing_events_processor = mock_processor
        return adapter

    @pytest.mark.asyncio
    @pytest.mark.filterwarnings("ignore::RuntimeWarning")
    async def test_start(self, adapter):
        """Test starting the adapter"""
        with patch("asyncio.create_task", return_value=MagicMock()):
            await adapter.start()

            assert adapter.running is True
            assert adapter.monitoring_task is not None
            assert adapter.session_manager is not None
            assert adapter.outgoing_events_processor is not None

            adapter.socketio_server.emit_event.assert_awaited_once_with(
                "connect", {"adapter_type": adapter.adapter_type}
            )

    @pytest.mark.asyncio
    @pytest.mark.filterwarnings("ignore::RuntimeWarning")
    async def test_stop(self, adapter):
        """Test stopping the adapter when it's running"""
        adapter.running = True
        adapter.monitoring_task = asyncio.create_task(asyncio.sleep(10))
        adapter.monitoring_task.cancel = MagicMock()

        await adapter.stop()

        assert adapter.running is False
        adapter.session_manager.stop.assert_awaited_once()
        adapter.monitoring_task.cancel.assert_called_once()
        adapter.socketio_server.emit_event.assert_awaited_once_with(
            "disconnect", {"adapter_type": adapter.adapter_type}
        )

    @pytest.mark.asyncio
    @pytest.mark.filterwarnings("ignore::RuntimeWarning")
    async def test_monitor_connection(self, adapter):
        """Test the connection monitor loop"""
        adapter.running = True

        with patch("asyncio.sleep", side_effect=[None, asyncio.CancelledError()]):
            with patch.object(adapter, "_emit_event") as mock_emit:
                try:
                    await adapter._monitor_connection()
                except asyncio.CancelledError:
                    pass

                mock_emit.assert_called_once_with("connect")

    @pytest.mark.asyncio
    async def test_emit_event(self, adapter):
        """Test emitting an event"""
        event_type = "test_event"

        await adapter._emit_event(event_type)

        adapter.socketio_server.emit_event.assert_awaited_once_with(
            event_type, {"adapter_type": adapter.adapter_type}
        )

    @pytest.mark.asyncio
    async def test_process_outgoing_event_success(self, adapter):
        """Test successful processing of outgoing events"""
        test_data = {"event_type": "execute_command", "data": {"command": "ls -la"}}
        result = await adapter.process_outgoing_event(test_data)

        assert result["request_completed"] is True
        adapter.outgoing_events_processor.process_event.assert_awaited_once_with(test_data)
