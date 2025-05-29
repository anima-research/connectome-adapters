import pytest
import os
import logging
from unittest.mock import MagicMock, AsyncMock, patch
from enum import Enum

from adapters.shell_adapter.adapter.event_processor.processor import Processor, FileEventType
from adapters.shell_adapter.adapter.event_processor.outgoing_events import OutgoingEventBuilder
from adapters.shell_adapter.adapter.session.manager import Manager
from adapters.shell_adapter.adapter.shell.metadata_fetcher import MetadataFetcher

class TestProcessor:
    """Tests for the Shell Adapter Processor class"""

    @pytest.fixture
    def mock_config(self):
        """Create a mock config for testing"""
        config = MagicMock()
        config.get_setting.side_effect = lambda section, key: {
            ("adapter", "workspace_directory"): "/home/user/workspace",
            ("adapter", "command_max_lifetime"): 60,
            ("adapter", "session_max_lifetime"): 120,
            ("adapter", "cpu_percent_limit"): 80,
            ("adapter", "memory_mb_limit"): 500
        }.get((section, key))
        return config

    @pytest.fixture
    def mock_session_manager(self):
        """Create a mock session manager"""
        session_manager = AsyncMock(spec=Manager)
        session_manager.open_session = AsyncMock(return_value="test-session-id")
        session_manager.close_session = AsyncMock()
        session_manager.run_command = AsyncMock(return_value={
            "stdout": "command output",
            "stderr": "",
            "exit_code": 0
        })
        return session_manager

    @pytest.fixture
    def mock_metadata_fetcher(self):
        """Create a mock metadata fetcher"""
        metadata_fetcher = MagicMock(spec=MetadataFetcher)
        metadata_fetcher.fetch = MagicMock(return_value={
            "operating_system": "Linux Test 1.0",
            "shell": "bash 5.1.16",
            "workspace_directory": "/home/user/workspace"
        })
        return metadata_fetcher

    @pytest.fixture
    def processor(self, mock_config, mock_session_manager, mock_metadata_fetcher):
        """Create a processor with mocked dependencies"""
        processor = Processor(mock_config, mock_session_manager)
        processor.metadata_fetcher = mock_metadata_fetcher
        return processor

    class TestInitialization:
        """Tests for initialization"""

        def test_initialization(self, mock_config, mock_session_manager):
            """Test that the processor initializes properly"""
            processor = Processor(mock_config, mock_session_manager)

            assert processor.config == mock_config
            assert processor.session_manager == mock_session_manager
            assert isinstance(processor.outgoing_event_builder, OutgoingEventBuilder)

    class TestOpenSessionEvent:
        """Tests for open_session event event"""

        @pytest.mark.asyncio
        async def test_process_event_open_session(self, processor, ):
            """Test processing an open_session event"""
            event_data = {"event_type": "open_session", "data": {}}

            with patch.object(
                processor, "_handle_open_session_event",
                return_value={"request_completed": True, "session_id": "test-session-id"}
            ) as mock_handler:
                result = await processor.process_event(event_data)

                mock_handler.assert_called_once()
                assert result["request_completed"] is True
                assert result["session_id"] == "test-session-id"

        @pytest.mark.asyncio
        async def test_open_session_success(self, processor, mock_session_manager):
            """Test successfully opening a session"""
            mock_session_manager.open_session.return_value = "new-session-id"

            result = await processor._handle_open_session_event(MagicMock())

            assert result["request_completed"] is True
            assert result["session_id"] == "new-session-id"
            mock_session_manager.open_session.assert_called_once()

        @pytest.mark.asyncio
        async def test_open_session_exception(self, processor, mock_session_manager):
            """Test handling an exception when opening a session"""
            mock_session_manager.open_session.side_effect = Exception("Test error")

            with patch("logging.error") as mock_log_error:
                result = await processor._handle_open_session_event(MagicMock())

                assert result["request_completed"] is False
                mock_log_error.assert_called_once()
                assert "Test error" in str(mock_log_error.call_args)

    class TestCloseSessionEvent:
        """Tests for close_session event event"""

        @pytest.mark.asyncio
        async def test_process_event_close_session(self, processor):
            """Test processing a close_session event"""
            event_data = {
                "event_type": "close_session",
                "data": {"session_id": "test-session-id"}
            }

            with patch.object(
                processor, "_handle_close_session_event",
                return_value={"request_completed": True}
            ) as mock_handler:
                result = await processor.process_event(event_data)

                mock_handler.assert_called_once()
                assert result["request_completed"] is True

        @pytest.mark.asyncio
        async def test_close_session_success(self, processor, mock_session_manager):
            """Test successfully closing a session"""
            data = MagicMock()
            data.session_id = "test-session-id"

            result = await processor._handle_close_session_event(data)

            assert result["request_completed"] is True
            mock_session_manager.close_session.assert_called_once_with("test-session-id")

        @pytest.mark.asyncio
        async def test_close_session_exception(self, processor, mock_session_manager):
            """Test handling an exception when closing a session"""
            data = MagicMock()
            data.session_id = "test-session-id"
            mock_session_manager.close_session.side_effect = Exception("Test error")

            with patch("logging.error") as mock_log_error:
                result = await processor._handle_close_session_event(data)

                assert result["request_completed"] is False
                mock_log_error.assert_called_once()
                assert "Test error" in str(mock_log_error.call_args)

    class TestHandleExecuteCommandEvent:
        """Tests for _handle_execute_command_event method"""

        @pytest.mark.asyncio
        async def test_process_event_execute_command(self, processor):
            """Test processing an execute_command event"""
            event_data = {
                "event_type": "execute_command",
                "data": {"command": "ls -la", "session_id": "test-session-id"}
            }

            expected_result = {
                "request_completed": True,
                "metadata": {"stdout": "command output", "stderr": "", "exit_code": 0}
            }

            with patch.object(
                processor, "_handle_execute_command_event",
                return_value=expected_result
            ) as mock_handler:
                result = await processor.process_event(event_data)

                mock_handler.assert_called_once()
                assert result["request_completed"] is True
                assert result["metadata"] == expected_result["metadata"]

        @pytest.mark.asyncio
        async def test_execute_command_with_session_id(self, processor, mock_session_manager):
            """Test executing a command with an existing session ID"""
            data = MagicMock()
            data.command = "echo hello"
            data.session_id = "existing-session-id"

            command_result = {
                "stdout": "hello",
                "stderr": "",
                "exit_code": 0
            }
            mock_session_manager.run_command.return_value = command_result

            result = await processor._handle_execute_command_event(data)

            assert result["request_completed"] is True
            assert result["metadata"] == command_result
            mock_session_manager.run_command.assert_called_once_with("existing-session-id", "echo hello")
            mock_session_manager.open_session.assert_not_called()
            mock_session_manager.close_session.assert_not_called()

        @pytest.mark.asyncio
        async def test_execute_command_without_session_id(self, processor, mock_session_manager):
            """Test executing a command without a session ID (temporary session)"""
            data = MagicMock()
            data.command = "echo hello"
            data.session_id = None

            command_result = {
                "stdout": "hello",
                "stderr": "",
                "exit_code": 0
            }
            mock_session_manager.run_command.return_value = command_result
            mock_session_manager.open_session.return_value = "temp-session-id"

            result = await processor._handle_execute_command_event(data)

            assert result["request_completed"] is True
            assert result["metadata"] == command_result
            mock_session_manager.open_session.assert_called_once()
            mock_session_manager.run_command.assert_called_once_with("temp-session-id", "echo hello")
            mock_session_manager.close_session.assert_called_once_with("temp-session-id")

        @pytest.mark.asyncio
        async def test_execute_command_exception(self, processor, mock_session_manager):
            """Test handling an exception when executing a command"""
            data = MagicMock()
            data.command = "invalid command"
            data.session_id = "test-session-id"

            mock_session_manager.run_command.side_effect = Exception("Test error")

            with patch("logging.error") as mock_log_error:
                result = await processor._handle_execute_command_event(data)

                assert result["request_completed"] is False
                mock_log_error.assert_called_once()
                assert "Test error" in str(mock_log_error.call_args)

    class TestHandleShellMetadataEvent:
        """Tests for _handle_shell_metadata_event method"""

        @pytest.mark.asyncio
        async def test_process_event_shell_metadata(self, processor):
            """Test processing a shell_metadata event"""
            event_data = {"event_type": "shell_metadata", "data": {}}

            expected_metadata = {
                "operating_system": "Linux Test 1.0",
                "shell": "bash 5.1.16",
                "workspace_directory": "/home/user/workspace"
            }

            with patch.object(
                processor, "_handle_shell_metadata_event",
                return_value={"request_completed": True, "metadata": expected_metadata}
            ) as mock_handler:
                result = await processor.process_event(event_data)

                mock_handler.assert_called_once()
                assert result["request_completed"] is True
                assert result["metadata"] == expected_metadata

        @pytest.mark.asyncio
        async def test_shell_metadata_success(self, processor):
            """Test successfully getting shell metadata"""
            expected_metadata = {
                "operating_system": "Linux Test 1.0",
                "shell": "bash 5.1.16",
                "workspace_directory": "/home/user/workspace"
            }
            processor.metadata_fetcher.fetch.return_value = expected_metadata

            result = await processor._handle_shell_metadata_event(MagicMock())

            assert result["request_completed"] is True
            assert result["metadata"] == expected_metadata
            processor.metadata_fetcher.fetch.assert_called_once()

        @pytest.mark.asyncio
        async def test_shell_metadata_exception(self, processor):
            """Test handling an exception when getting shell metadata"""
            processor.metadata_fetcher.fetch.side_effect = Exception("Metadata error")

            with patch("logging.error") as mock_log_error:
                result = await processor._handle_shell_metadata_event(MagicMock())

                assert result["request_completed"] is False
                mock_log_error.assert_called_once()
                assert "Metadata error" in str(mock_log_error.call_args)
