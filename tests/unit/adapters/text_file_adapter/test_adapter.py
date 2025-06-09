import pytest
import asyncio
import os
import tempfile
import shutil
from unittest.mock import AsyncMock, MagicMock, patch

from src.adapters.text_file_adapter.adapter import Adapter
from src.adapters.text_file_adapter.event_processor.processor import Processor
from src.adapters.text_file_adapter.event_processor.file_event_cache import FileEventCache

class TestFileAdapter:
    """Tests for the Text File Adapter class"""

    @pytest.fixture
    def socketio_server_mock(self):
        """Create a mocked Socket.IO server"""
        server = AsyncMock()
        server.emit_event = AsyncMock()
        return server

    @pytest.fixture
    def file_event_cache_mock(self):
        """Create a mocked FileEventCache"""
        cache = AsyncMock(spec=FileEventCache)
        cache.start = AsyncMock()
        cache.stop = AsyncMock()
        return cache

    @pytest.fixture
    def processor_mock(self):
        """Create a mocked Processor"""
        processor = AsyncMock(spec=Processor)
        processor.process_event = AsyncMock(
            return_value={"request_completed": True}
        )
        return processor

    @pytest.fixture
    def test_directory(self):
        """Create a temporary test directory"""
        test_dir = tempfile.mkdtemp()
        yield test_dir
        shutil.rmtree(test_dir)

    @pytest.fixture
    def zulip_config(self, test_directory):
        """Create a mock config"""
        config = MagicMock()
        config.get_setting.side_effect = lambda section, key: {
            ("adapter", "max_file_size"): 1,
            ("adapter", "adapter_type"): "file",
            ("adapter", "connection_check_interval"): 1,
            ("adapter", "backup_directory"): os.path.join(test_directory, "backups"),
            ("adapter", "event_ttl_hours"): 24,
            ("adapter", "cleanup_interval_hours"): 1,
            ("adapter", "max_events_per_file"): 5
        }.get((section, key))
        return config

    @pytest.fixture
    def adapter(self, socketio_server_mock, file_event_cache_mock, processor_mock, zulip_config):
        """Create a Text File Adapter with mocked dependencies"""
        adapter = Adapter(zulip_config, socketio_server_mock)
        adapter.file_event_cache = file_event_cache_mock
        adapter.outgoing_events_processor = processor_mock
        return adapter

    @pytest.mark.asyncio
    @pytest.mark.filterwarnings("ignore::RuntimeWarning")
    async def test_start(self, adapter):
        """Test starting the adapter"""
        with patch('asyncio.create_task', return_value=MagicMock()):
            await adapter.start()

            assert adapter.running is True
            assert adapter.monitoring_task is not None
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
        adapter.file_event_cache = AsyncMock()

        await adapter.stop()

        assert adapter.running is False
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
    async def test_process_outgoing_event_success(self, adapter):
        """Test successful processing of outgoing events"""
        test_data = {
            "event_type": "create",
            "data": {"path": "/path/to/file.txt", "content": "Test content"}
        }
        result = await adapter.process_outgoing_event(test_data)

        assert result["request_completed"] is True
        adapter.outgoing_events_processor.process_event.assert_awaited_once_with(test_data)
