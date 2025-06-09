import pytest
import asyncio
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, AsyncMock, call

from src.adapters.shell_adapter.session.command_executor import CommandExecutor
from src.adapters.shell_adapter.session.session import Session

class TestCommandExecutor:
    """Tests for the Shell Command Executor class"""

    @pytest.fixture
    def mock_config(self):
        """Create a mock config for testing"""
        config = MagicMock()
        config.get_setting.side_effect = lambda section, key: {
            ("adapter", "workspace_directory"): "/home/user/workspace",
            ("adapter", "max_output_size"): 10000,
            ("adapter", "begin_output_size"): 4000,
            ("adapter", "end_output_size"): 4000,
            ("adapter", "command_max_lifetime"): 60,
            ("adapter", "cpu_percent_limit"): 80,
            ("adapter", "memory_mb_limit"): 500,
            ("adapter", "disk_mb_limit"): 1000
        }.get((section, key))
        return config

    @pytest.fixture
    def mock_session(self):
        """Create a mock Session"""
        session = AsyncMock(spec=Session)
        session.session_id = str(uuid.uuid4())
        session.execute_command = AsyncMock()
        session.update_working_directory = AsyncMock(return_value="/home/user/workspace")
        session.get_resource_usage = AsyncMock(return_value={
            "cpu_percent": 10.0,
            "memory_mb": 100.0
        })
        return session

    @pytest.fixture
    def command_executor(self, mock_config):
        """Create a CommandExecutor with mocked dependencies"""
        return CommandExecutor(mock_config)

    class TestInitialization:
        """Tests for the initialization process"""

        def test_initialization(self, mock_config):
            """Test that the executor initializes properly"""
            executor = CommandExecutor(mock_config)

            assert executor.config == mock_config
            assert executor.command_tasks == {}
            assert executor.workspace_directory == "/home/user/workspace"
            assert executor.max_output_size == 10000
            assert executor.begin_output_size == 4000
            assert executor.end_output_size == 4000
            assert executor.command_max_lifetime == 60
            assert executor.cpu_limit == 80
            assert executor.memory_limit_mb == 500
            assert executor.disk_limit_mb == 1000

    class TestCleanup:
        """Tests for the cleanup method"""

        def test_del_method(self, command_executor):
            """Test that the __del__ method cancels running tasks"""
            mock_task1 = AsyncMock()
            mock_task1.cancel = MagicMock()
            mock_task2 = AsyncMock()
            mock_task2.cancel = MagicMock()

            command_executor.command_tasks = {
                "cmd1": {"task": mock_task1, "command": "test1", "session": MagicMock()},
                "cmd2": {"task": mock_task2, "command": "test2", "session": MagicMock()}
            }

            command_executor.__del__()

            mock_task1.cancel.assert_called_once()
            mock_task2.cancel.assert_called_once()

    class TestExecute:
        """Tests for the execute method"""

        @pytest.mark.asyncio
        async def test_execute_command_success_alternative(self, command_executor, mock_session):
            """Test executing a command successfully - alternative approach"""
            command = "echo hello"
            command_result = {
                "stdout": "hello\n",
                "stderr": "",
                "exit_code": 0
            }
            mock_session.execute_command.return_value = command_result

            with patch.object(command_executor, "_monitor_command_resources") as mock_monitor, \
                patch("uuid.uuid4") as mock_uuid:

                mock_uuid.return_value = "test-command-id"
                mock_monitor.return_value = None

                result = await command_executor.execute(command, mock_session)

                mock_session.execute_command.assert_called_once_with(command)

                assert mock_monitor.call_count == 1
                monitor_args = mock_monitor.call_args[0]
                assert monitor_args[0] == "test-command-id"  # command_id
                assert monitor_args[2] == mock_session  # session


                mock_session.update_working_directory.assert_called_once()

                assert result["stdout"] == "hello\n"
                assert result["stderr"] == ""
                assert result["exit_code"] == 0
                assert result["new_working_directory"] == "/home/user/workspace"
                assert result["unsuccessful"] is False

        @pytest.mark.asyncio
        async def test_execute_command_cancelled(self, command_executor, mock_session):
            """Test executing a command that gets cancelled"""
            command = "sleep 100"
            mock_session.execute_command.side_effect = asyncio.CancelledError()

            with patch.object(command_executor, "_monitor_command_resources") as mock_monitor, \
                patch("uuid.uuid4") as mock_uuid:

                mock_uuid.return_value = "test-command-id"
                result = await command_executor.execute(command, mock_session)

                mock_session.execute_command.assert_called_once_with(command)
                mock_monitor.assert_called_once()

                assert result["unsuccessful"] is True
                mock_session.update_working_directory.assert_called_once()

    class TestMonitorCommandResources:
        """Tests for the _monitor_command_resources method"""

        @pytest.mark.asyncio
        async def test_monitor_normal_execution(self, command_executor, mock_session):
            """Test monitoring a command that completes normally"""
            command_id = "test-command-id"
            execution_task = AsyncMock()
            execution_task.done = MagicMock(side_effect=[False, True])

            with patch("asyncio.sleep", new_callable=AsyncMock):
                await command_executor._monitor_command_resources(
                    command_id, execution_task, mock_session
                )

                mock_session.get_resource_usage.assert_called_once()
                execution_task.cancel.assert_not_called()

        @pytest.mark.asyncio
        async def test_monitor_limit_exceeded(self, command_executor, mock_session):
            """Test monitoring a command that exceeds CPU limit. Same works for memory limit."""
            command_id = "test-command-id"
            execution_task = AsyncMock()
            execution_task.done = MagicMock(return_value = False)
            execution_task.cancel = MagicMock()

            mock_session.get_resource_usage.return_value = {
                "cpu_percent": command_executor.cpu_limit + 10,
                "memory_mb": 100.0
            }

            with patch("asyncio.sleep", new_callable=AsyncMock):
                await command_executor._monitor_command_resources(
                    command_id, execution_task, mock_session
                )

                # Verify execution task was cancelled
                execution_task.cancel.assert_called_once()

    class TestFormatOutput:
        """Tests for the _format_output method"""

        def test_format_output_normal(self, command_executor):
            """Test formatting output that doesn't need truncation"""
            cmd_result = {
                "stdout": "hello\n",
                "stderr": "",
                "exit_code": 0,
                "new_working_directory": "/home/user/workspace",
                "unsuccessful": False
            }

            result = command_executor._format_output(cmd_result)

            assert result["stdout"] == "hello\n"
            assert result["stderr"] == ""
            assert result["exit_code"] == 0
            assert result["new_working_directory"] == "/home/user/workspace"
            assert result["unsuccessful"] is False
            assert result["original_stdout_size"] is None
            assert result["original_stderr_size"] is None

        def test_format_output_truncation(self, command_executor):
            """Test formatting output that needs truncation"""
            large_stdout = "a" * (command_executor.max_output_size + 1000)

            cmd_result = {
                "stdout": large_stdout,
                "stderr": "",
                "exit_code": 0
            }

            result = command_executor._format_output(cmd_result)

            assert len(result["stdout"]) < len(large_stdout)
            assert "[Output truncated]" in result["stdout"]
            assert result["original_stdout_size"] == len(large_stdout)
            assert result["stdout"].startswith("a" * 100)  # Beginning part
            assert result["stdout"].endswith("a" * 100)    # Ending part

        def test_format_output_missing_fields(self, command_executor):
            """Test formatting output with missing fields"""
            cmd_result = {
                "stdout": "hello\n",
                "exit_code": 0
                # Missing stderr, new_working_directory, unsuccessful
            }

            result = command_executor._format_output(cmd_result)

            # Verify default values used for missing fields
            assert result["stderr"] == ""
            assert result["new_working_directory"] is None
            assert result["unsuccessful"] is False

    class TestTruncateText:
        """Tests for the _truncate_text method"""

        def test_truncate_text_no_truncation_needed(self, command_executor):
            """Test truncating text that doesn't need truncation"""
            text = "short text"
            truncated, original_size = command_executor._truncate_text(text)

            # Verify text wasn't changed and original size is None
            assert truncated == text
            assert original_size is None

        def test_truncate_text_truncation_needed(self, command_executor):
            """Test truncating text that needs truncation"""
            # Override max_output_size for this test
            command_executor.max_output_size = 20
            command_executor.begin_output_size = 5
            command_executor.end_output_size = 5

            text = "this is a long text that needs truncation"
            truncated, original_size = command_executor._truncate_text(text)

            # Verify text was truncated
            assert len(truncated) < len(text)
            assert "[Output truncated]" in truncated
            assert original_size == len(text)

            # Verify truncation format
            assert truncated.startswith("this ")
            assert truncated.endswith("ation")

        def test_truncate_text_exact_size(self, command_executor):
            """Test truncating text that is exactly max_output_size"""
            # Override max_output_size for this test
            command_executor.max_output_size = 20

            text = "exactly twenty chars"  # 20 characters
            truncated, original_size = command_executor._truncate_text(text)

            # Verify text wasn't changed and original size is None
            assert truncated == text
            assert original_size is None
