import asyncio
import os
import platform
import psutil
import pytest
import signal
import uuid

from unittest.mock import MagicMock, patch, AsyncMock
from adapters.shell_adapter.adapter.session.session import Session

class TestSession:
    """Tests for the Shell Session class"""

    @pytest.fixture
    def workspace_directory(self):
        """Create a workspace directory for testing"""
        return "/home/user/workspace"

    @pytest.fixture
    def session_id(self):
        """Create a session ID for testing"""
        return "test-session-id"

    @pytest.fixture
    def mock_process(self):
        """Create a mock subprocess process"""
        process = MagicMock()
        process.pid = 12345
        process.returncode = None
        process.stdin = AsyncMock()
        process.stdin.write = MagicMock()
        process.stdin.drain = AsyncMock()
        process.stdout = AsyncMock()
        process.stderr = AsyncMock()
        return process

    class TestInitialization:
        """Tests for the initialization process"""

        def test_initialization(self, workspace_directory, session_id):
            """Test that the session initializes properly"""
            session = Session(workspace_directory, session_id)

            assert session.workspace_directory == workspace_directory
            assert session.session_id == session_id
            assert session.process is None
            assert session.pgid is None
            assert session.system == platform.system()

            # Test shell command and line ending based on platform
            if platform.system() == "Windows":
                assert session.shell_command == "cmd.exe"
                assert session.line_ending == "\r\n"
            else:
                assert session.shell_command in [os.environ.get("SHELL", "/bin/bash"), "/bin/bash"]
                assert session.line_ending == "\n"

            assert session.marker is None
            assert session.exit_code_marker is None
            assert session.full_command is None
            assert session.last_state == {
                "stdout": "",
                "stderr": "Error executing command",
                "exit_code": -1
            }

        def test_initialization_without_session_id(self, workspace_directory):
            """Test initialization without a session ID"""
            with patch("uuid.uuid4") as mock_uuid:
                mock_uuid.return_value.hex = "generated-session-id"
                session = Session(workspace_directory)

                assert session.session_id == "generated-session-id"

    class TestOpen:
        """Tests for opening a session"""

        @pytest.mark.asyncio
        async def test_open_unix(self, workspace_directory, session_id, mock_process):
            """Test opening a session on Unix-like systems"""
            with patch("platform.system", return_value="Linux"), \
                 patch("asyncio.create_subprocess_shell", return_value=mock_process), \
                 patch("os.getpgid", return_value=12345), \
                 patch.object(Session, "_setup_shell_process") as mock_setup, \
                 patch.object(Session, "_drain_output") as mock_drain:

                session = Session(workspace_directory, session_id)
                result = await session.open()

                asyncio.create_subprocess_shell.assert_called_once()
                assert "start_new_session=True" in str(asyncio.create_subprocess_shell.call_args)

                assert session.process == mock_process
                assert session.pgid == 12345

                mock_setup.assert_called_once()
                mock_drain.assert_called_once()

                assert result == session

        @pytest.mark.asyncio
        async def test_open_windows(self, workspace_directory, session_id, mock_process):
            """Test opening a session on Windows"""
            with patch("platform.system", return_value="Windows"), \
                 patch("asyncio.create_subprocess_shell", return_value=mock_process), \
                 patch.object(Session, "_setup_shell_process") as mock_setup, \
                 patch.object(Session, "_drain_output") as mock_drain:

                session = Session(workspace_directory, session_id)
                result = await session.open()

                asyncio.create_subprocess_shell.assert_called_once()
                assert "start_new_session=True" not in str(asyncio.create_subprocess_shell.call_args)

                assert session.process == mock_process
                assert session.pgid == mock_process.pid

                mock_setup.assert_called_once()
                mock_drain.assert_called_once()

                assert result == session

    class TestClose:
        """Tests for closing a session"""

        @pytest.mark.asyncio
        async def test_close_without_process(self, workspace_directory, session_id):
            """Test closing a session without a process"""
            session = Session(workspace_directory, session_id)
            session.process = None

            # Should not raise any exceptions
            await session.close()

        @pytest.mark.asyncio
        async def test_close_unix(self, workspace_directory, session_id, mock_process):
            """Test closing a session on Unix-like systems"""
            mock_children = [MagicMock() for _ in range(2)]
            mock_psutil_process = MagicMock()
            mock_psutil_process.children.return_value = mock_children

            with patch("platform.system", return_value="Linux"), \
                 patch("psutil.Process", return_value=mock_psutil_process), \
                 patch("os.killpg") as mock_killpg:

                session = Session(workspace_directory, session_id)
                session.process = mock_process
                session.pgid = 12345

                await session.close()

                mock_killpg.assert_called_once_with(12345, signal.SIGKILL)

        @pytest.mark.asyncio
        async def test_close_unix_fallback(self, workspace_directory, session_id, mock_process):
            """Test closing a session on Unix with fallback to killing individual processes"""
            mock_children = [MagicMock() for _ in range(2)]
            mock_psutil_process = MagicMock()
            mock_psutil_process.children.return_value = mock_children

            with patch("platform.system", return_value="Linux"), \
                 patch("psutil.Process", return_value=mock_psutil_process), \
                 patch("os.killpg", side_effect=Exception("Test error")):

                session = Session(workspace_directory, session_id)
                session.process = mock_process
                session.pgid = 12345

                await session.close()

                for child in mock_children:
                    child.kill.assert_called_once()
                mock_process.kill.assert_called_once()

        @pytest.mark.asyncio
        async def test_close_windows(self, workspace_directory, session_id, mock_process):
            """Test closing a session on Windows"""
            mock_children = [MagicMock() for _ in range(2)]
            mock_psutil_process = MagicMock()
            mock_psutil_process.children.return_value = mock_children

            with patch("platform.system", return_value="Windows"), \
                 patch("psutil.Process", return_value=mock_psutil_process):

                session = Session(workspace_directory, session_id)
                session.process = mock_process

                await session.close()

                for child in mock_children:
                    child.kill.assert_called_once()
                mock_process.kill.assert_called_once()

    class TestExecuteCommand:
        """Tests for executing commands"""

        @pytest.mark.asyncio
        async def test_execute_command(self, workspace_directory, session_id, mock_process):
            """Test executing a command successfully"""
            with patch.object(Session, "_setup_markers_and_command") as mock_setup_markers, \
                 patch.object(Session, "_setup_stdout_output_and_exit_code") as mock_setup_stdout, \
                 patch.object(Session, "_setup_stderr_output") as mock_setup_stderr:

                session = Session(workspace_directory, session_id)
                session.process = mock_process
                session.full_command = "echo hello\necho EXIT_CODE_123\necho MARKER_123\n"

                result = await session.execute_command("echo hello")

                mock_setup_markers.assert_called_once_with("echo hello")
                mock_process.stdin.write.assert_called_once_with(session.full_command.encode())
                mock_process.stdin.drain.assert_called_once()
                mock_setup_stdout.assert_called_once()
                mock_setup_stderr.assert_called_once()

                assert result == session.last_state

        @pytest.mark.asyncio
        async def test_execute_command_exception(self, workspace_directory, session_id, mock_process):
            """Test executing a command that raises an exception"""
            with patch.object(Session, "_setup_markers_and_command", side_effect=Exception("Test error")):
                session = Session(workspace_directory, session_id)
                session.process = mock_process

                result = await session.execute_command("echo hello")

                # Verify result is the default last_state
                assert result == session.last_state
                assert result["exit_code"] == -1
                assert "Error executing command" in result["stderr"]

    class TestUpdateWorkingDirectory:
        """Tests for updating the working directory"""

        @pytest.mark.asyncio
        async def test_update_working_directory_unix(self, workspace_directory, session_id, mock_process):
            """Test updating working directory on Unix"""
            mock_process.stdout.readline.side_effect = [
                "/home/user/newdir\n".encode(),
                "PWD_MARKER_123\n".encode()
            ]

            with patch("platform.system", return_value="Linux"), \
                 patch("uuid.uuid4") as mock_uuid:

                mock_uuid.return_value.hex = "123"

                session = Session(workspace_directory, session_id)
                session.process = mock_process

                result = await session.update_working_directory()
                assert mock_process.stdin.write.call_args.args[0].startswith(b"pwd; echo PWD_MARKER_123")

                assert session.workspace_directory == "/home/user/newdir"
                assert result == "/home/user/newdir"

        @pytest.mark.asyncio
        async def test_update_working_directory_windows(self, workspace_directory, session_id, mock_process):
            """Test updating working directory on Windows"""
            mock_process.stdout.readline.side_effect = [
                "C:\\Users\\user\\newdir\r\n".encode(),
                "PWD_MARKER_123\r\n".encode()
            ]

            with patch("platform.system", return_value="Windows"), \
                 patch("uuid.uuid4") as mock_uuid:

                mock_uuid.return_value.hex = "123"

                session = Session(workspace_directory, session_id)
                session.process = mock_process

                result = await session.update_working_directory()

                assert mock_process.stdin.write.call_args.args[0].startswith(b"cd\r\necho PWD_MARKER_123")

                assert session.workspace_directory == "C:\\Users\\user\\newdir"
                assert result == "C:\\Users\\user\\newdir"

        @pytest.mark.asyncio
        async def test_update_working_directory_no_output(self, workspace_directory, session_id, mock_process):
            """Test updating working directory when no output is returned"""
            mock_process.stdout.readline.side_effect = [
                "PWD_MARKER_123\n".encode()
            ]

            with patch("platform.system", return_value="Linux"), \
                 patch("uuid.uuid4") as mock_uuid:

                mock_uuid.return_value.hex = "123"

                session = Session(workspace_directory, session_id)
                session.process = mock_process

                result = await session.update_working_directory()

                assert session.workspace_directory == workspace_directory
                assert result == workspace_directory

    class TestGetResourceUsage:
        """Tests for getting resource usage"""

        @pytest.mark.asyncio
        async def test_get_resource_usage(self, workspace_directory, session_id, mock_process):
            """Test getting resource usage"""
            mock_child1 = MagicMock()
            mock_child1.cpu_percent.return_value = 5.0
            mock_child1.memory_info().rss = 50 * 1024 * 1024  # 50 MB

            mock_child2 = MagicMock()
            mock_child2.cpu_percent.return_value = 10.0
            mock_child2.memory_info().rss = 100 * 1024 * 1024  # 100 MB

            mock_psutil_process = MagicMock()
            mock_psutil_process.cpu_percent.return_value = 15.0
            mock_psutil_process.memory_info().rss = 200 * 1024 * 1024  # 200 MB
            mock_psutil_process.children.return_value = [mock_child1, mock_child2]

            with patch("psutil.Process", return_value=mock_psutil_process):
                session = Session(workspace_directory, session_id)
                session.process = mock_process

                result = await session.get_resource_usage()

                assert result["cpu_percent"] == 30.0  # 15 + 5 + 10
                assert result["memory_mb"] == 350.0  # 200 + 50 + 100 MB

        @pytest.mark.asyncio
        async def test_get_resource_usage_exception(self, workspace_directory, session_id, mock_process):
            """Test getting resource usage when an exception occurs"""
            with patch("psutil.Process", side_effect=Exception("Test error")):
                session = Session(workspace_directory, session_id)
                session.process = mock_process

                result = await session.get_resource_usage()

                assert result["cpu_percent"] == 0.0
                assert result["memory_mb"] == 0.0

        @pytest.mark.asyncio
        async def test_get_resource_usage_child_exception(self, workspace_directory, session_id, mock_process):
            """Test getting resource usage when child process access raises exception"""
            session = Session(workspace_directory, session_id)
            session.process = mock_process

            mock_psutil_process = MagicMock()
            mock_psutil_process.cpu_percent.return_value = 15.0
            mock_psutil_process.memory_info().rss = 200 * 1024 * 1024  # 200 MB

            child1 = MagicMock()
            child1.cpu_percent.side_effect = psutil.NoSuchProcess(pid=9998)
            child1.memory_info.side_effect = psutil.AccessDenied()
            child2 = MagicMock()
            child2.cpu_percent.side_effect = psutil.NoSuchProcess(pid=9999)
            child2.memory_info.side_effect = psutil.AccessDenied()
            mock_psutil_process.children.return_value = [child1, child2]

            with patch("psutil.Process", return_value=mock_psutil_process):
                result = await session.get_resource_usage()

                # Verify only the main process resources are counted
                assert result["cpu_percent"] == 15.0
                assert result["memory_mb"] == 200.0

    class TestSetupShellProcess:
        """Tests for setting up the shell process"""

        @pytest.mark.asyncio
        async def test_setup_shell_process_unix(self, workspace_directory, session_id, mock_process):
            """Test setting up the shell process on Unix"""
            with patch("platform.system", return_value="Linux"), \
                 patch("shlex.quote", return_value="'/home/user/workspace'"):

                session = Session(workspace_directory, session_id)
                session.process = mock_process

                await session._setup_shell_process()

                # Verify all setup commands were sent
                calls = mock_process.stdin.write.call_args_list
                assert len(calls) == 4
                assert b"export SHELL_ADAPTER_SESSION=1" in calls[0].args[0]
                assert b"export SHELL_ADAPTER_SESSION_ID=test-session-id" in calls[1].args[0]
                assert b"export PS1='$ '" in calls[2].args[0]
                assert b"cd '/home/user/workspace'" in calls[3].args[0]

                # Verify drain called after each command
                assert mock_process.stdin.drain.call_count == 4

        @pytest.mark.asyncio
        async def test_setup_shell_process_windows(self, workspace_directory, session_id, mock_process):
            """Test setting up the shell process on Windows"""
            with patch("platform.system", return_value="Windows"):
                session = Session(workspace_directory, session_id)
                session.process = mock_process

                await session._setup_shell_process()

                # Verify all setup commands were sent
                calls = mock_process.stdin.write.call_args_list
                assert len(calls) == 4
                assert b"set SHELL_ADAPTER_SESSION=1" in calls[0].args[0]
                assert b"set SHELL_ADAPTER_SESSION_ID=test-session-id" in calls[1].args[0]
                assert b"prompt $$ " in calls[2].args[0]
                assert b"cd /d /home/user/workspace" in calls[3].args[0]

                # Verify drain called after each command
                assert mock_process.stdin.drain.call_count == 4

    class TestDrainOutput:
        """Tests for draining output"""

        @pytest.mark.asyncio
        async def test_drain_output(self, workspace_directory, session_id, mock_process):
            """Test draining output"""
            mock_process.stdout.readline.side_effect = [
                "some output\n".encode(),
                "more output\n".encode(),
                "DRAIN_MARKER_123\n".encode()
            ]

            with patch("uuid.uuid4") as mock_uuid:
                mock_uuid.return_value.hex = "123"

                session = Session(workspace_directory, session_id)
                session.process = mock_process

                await session._drain_output()

                # Verify marker command was sent
                assert mock_process.stdin.write.call_args.args[0].startswith(b"echo DRAIN_MARKER_123")
                # Verify stdout was read until marker
                assert mock_process.stdout.readline.call_count == 3
                # Verify stderr was drained
                assert mock_process.stderr.readline.call_count > 0

        @pytest.mark.asyncio
        async def test_drain_output_eof(self, workspace_directory, session_id, mock_process):
            """Test draining output when EOF is encountered"""
            mock_process.stdout.readline.side_effect = [
                "some output\n".encode(),
                b""  # EOF
            ]

            with patch("uuid.uuid4") as mock_uuid:
                mock_uuid.return_value.hex = "123"

                session = Session(workspace_directory, session_id)
                session.process = mock_process

                await session._drain_output()

                # Verify stdout was read until EOF
                assert mock_process.stdout.readline.call_count == 2

    class TestSetupMarkersAndCommand:
        """Tests for setting up markers and command"""

        def test_setup_markers_and_command_unix(self, workspace_directory, session_id):
            """Test setting up markers and command on Unix"""
            with patch("platform.system", return_value="Linux"), \
                 patch("uuid.uuid4") as mock_uuid:

                mock_uuid.return_value.hex = "123"

                session = Session(workspace_directory, session_id)
                session._setup_markers_and_command("echo hello")

                # Verify markers were set
                assert session.marker == "CMD_MARKER_123"
                assert session.exit_code_marker == "EXIT_CODE_123"

                # Verify command was formatted correctly
                expected_command = "echo hello\necho EXIT_CODE_123$?\necho CMD_MARKER_123\n"
                assert session.full_command == expected_command

        def test_setup_markers_and_command_windows(self, workspace_directory, session_id):
            """Test setting up markers and command on Windows"""
            with patch("platform.system", return_value="Windows"), \
                 patch("uuid.uuid4") as mock_uuid:

                mock_uuid.return_value.hex = "123"

                session = Session(workspace_directory, session_id)
                session._setup_markers_and_command("echo hello")

                # Verify markers were set
                assert session.marker == "CMD_MARKER_123"
                assert session.exit_code_marker == "EXIT_CODE_123"

                # Verify command was formatted correctly
                expected_command = "echo hello\r\necho EXIT_CODE_123%ERRORLEVEL%\r\necho CMD_MARKER_123\r\n"
                assert session.full_command == expected_command

    class TestSetupStdoutOutputAndExitCode:
        """Tests for setting up stdout output and exit code"""

        @pytest.mark.asyncio
        async def test_setup_stdout_output_and_exit_code(self, workspace_directory, session_id, mock_process):
            """Test setting up stdout output and exit code"""
            mock_process.stdout.readline.side_effect = [
                "hello\n".encode(),
                "world\n".encode(),
                "EXIT_CODE_1230\n".encode(),  # Exit code 0
                "CMD_MARKER_123\n".encode()
            ]

            session = Session(workspace_directory, session_id)
            session.process = mock_process
            session.marker = "CMD_MARKER_123"
            session.exit_code_marker = "EXIT_CODE_123"

            await session._setup_stdout_output_and_exit_code()

            # Verify last_state was updated correctly
            assert session.last_state["stdout"] == "hello\nworld"
            assert session.last_state["exit_code"] == 0

        @pytest.mark.asyncio
        async def test_setup_stdout_output_eof(self, workspace_directory, session_id, mock_process):
            """Test setting up stdout output when EOF is encountered"""
            mock_process.stdout.readline.side_effect = [
                "hello\n".encode(),
                b""  # EOF
            ]

            session = Session(workspace_directory, session_id)
            session.process = mock_process
            session.marker = "CMD_MARKER_123"
            session.exit_code_marker = "EXIT_CODE_123"

            await session._setup_stdout_output_and_exit_code()

            assert session.last_state["stdout"] == "hello"
            assert session.last_state["exit_code"] == 0  # Default when not found

        @pytest.mark.asyncio
        async def test_setup_stdout_output_invalid_exit_code(self, workspace_directory, session_id, mock_process):
            """Test setting up stdout output with invalid exit code"""
            mock_process.stdout.readline.side_effect = [
                "hello\n".encode(),
                "EXIT_CODE_123invalid\n".encode(),  # Invalid exit code
                "CMD_MARKER_123\n".encode()
            ]

            session = Session(workspace_directory, session_id)
            session.process = mock_process
            session.marker = "CMD_MARKER_123"
            session.exit_code_marker = "EXIT_CODE_123"

            await session._setup_stdout_output_and_exit_code()

            # Verify last_state uses default exit code when invalid
            assert session.last_state["stdout"] == "hello"
            assert session.last_state["exit_code"] == 0  # Default when invalid

    class TestSetupStderrOutput:
        """Tests for setting up stderr output"""

        @pytest.mark.asyncio
        async def test_setup_stderr_output(self, workspace_directory, session_id, mock_process):
            """Test setting up stderr output"""
            error1 = "error 1\n".encode()
            error2 = "error 2\n".encode()

            mock_process.stderr.readline = AsyncMock()
            mock_process.stderr.readline.side_effect = [error1, error2, b""]

            session = Session(workspace_directory, session_id)
            session.process = mock_process

            async def mock_wait_for_impl(coro, _):
                return await coro

            with patch("asyncio.wait_for", side_effect=mock_wait_for_impl):
                await session._setup_stderr_output()

                # Verify last_state was updated correctly
                assert session.last_state["stderr"] == "error 1\nerror 2"

        @pytest.mark.asyncio
        async def test_setup_stderr_output_empty(self, workspace_directory, session_id, mock_process):
            """Test setting up stderr output when no stderr is available"""
            mock_process.stderr.readline.side_effect = asyncio.TimeoutError()

            session = Session(workspace_directory, session_id)
            session.process = mock_process

            with patch("asyncio.wait_for") as mock_wait_for:
                mock_wait_for.side_effect = asyncio.TimeoutError()

                await session._setup_stderr_output()

                # Verify last_state has empty stderr
                assert session.last_state["stderr"] == ""
