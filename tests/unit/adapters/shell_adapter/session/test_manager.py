import asyncio
import os
import pytest
import shutil
import uuid

from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime

from src.adapters.shell_adapter.session.command_executor import CommandExecutor
from src.adapters.shell_adapter.session.manager import Manager
from src.adapters.shell_adapter.session.session import Session

class TestManager:
    """Tests for the Shell Session Manager class"""

    @pytest.fixture(scope="class", autouse=True)
    def ensure_test_directories(self):
        """Create necessary test directories before tests and clean up after"""
        os.makedirs("/home/user/workspace", exist_ok=True)

        yield

        if os.path.exists("/home/user/workspace"):
            shutil.rmtree("/home/user/workspace")

    @pytest.fixture
    def mock_config(self):
        """Create a mock config for testing"""
        config = MagicMock()
        config.get_setting.side_effect = lambda section, key: {
            ("adapter", "session_max_lifetime"): 60,
            ("adapter", "workspace_directory"): "/home/user/workspace"
        }.get((section, key))
        return config

    @pytest.fixture
    def mock_session(self):
        """Create a mock Session"""
        session = AsyncMock(spec=Session)
        session.session_id = str(uuid.uuid4())
        session.process = MagicMock()
        session.process.returncode = None
        session.update_working_directory = AsyncMock(return_value="/home/user/workspace")
        session.close = AsyncMock()
        return session

    @pytest.fixture
    def mock_command_executor(self):
        """Create a mock CommandExecutor"""
        executor = MagicMock(spec=CommandExecutor)
        executor.execute = AsyncMock()
        return executor

    @pytest.fixture
    def session_manager(self, mock_config, mock_command_executor):
        """Create a SessionManager with mocked dependencies"""
        manager = Manager(mock_config)
        manager.command_executor = mock_command_executor
        return manager

    class TestInitialization:
        """Tests for the initialization process"""

        def test_initialization(self, mock_config):
            """Test that the manager initializes properly"""
            manager = Manager(mock_config)

            assert manager.config == mock_config
            assert manager.sessions == {}
            assert manager.sessions_with_running_commands == set()
            assert manager.running == False
            assert manager.cleanup_task is None
            assert manager.session_max_lifetime == 60
            assert manager.workspace_directory == "/home/user/workspace"

    class TestStartStop:
        """Tests for starting and stopping the manager"""

        @pytest.mark.asyncio
        async def test_start(self, session_manager):
            """Test starting the session manager"""
            with patch.object(asyncio, "create_task") as mock_create_task:
                await session_manager.start()

                assert session_manager.running == True
                mock_create_task.assert_not_called()

        @pytest.mark.asyncio
        async def test_start_with_maintenance(self, mock_config):
            """Test starting with maintenance enabled"""
            with patch.object(asyncio, "create_task") as mock_create_task:
                manager = Manager(mock_config, maintenance_required=True)
                await manager.start()

                assert manager.running == True
                mock_create_task.assert_called_once()

        @pytest.mark.asyncio
        @pytest.mark.filterwarnings("ignore::RuntimeWarning")
        async def test_stop(self, session_manager, mock_session):
            """Test stopping the session manager"""
            session_id = "test-session-id"
            session_manager.sessions = {
                session_id: {
                    "session": mock_session,
                    "created_at": datetime.now(),
                    "working_dir": "/home/user/workspace"
                }
            }

            with patch.object(session_manager, "close_session") as mock_close_session:
                mock_close_session.return_value = asyncio.Future()
                mock_close_session.return_value.set_result(None)

                await session_manager.stop()

                assert session_manager.running == False
                mock_close_session.assert_called_once_with(session_id)

        @pytest.mark.asyncio
        async def test_stop_with_cleanup_task(self, session_manager):
            """Test stopping with active cleanup task"""
            cleanup_task = MagicMock()
            cleanup_task.cancel = MagicMock()
            session_manager.cleanup_task = cleanup_task

            await session_manager.stop()

            cleanup_task.cancel.assert_called_once()

    class TestSessionManagement:
        """Tests for session management functionality"""

        @pytest.mark.asyncio
        async def test_open_session(self, session_manager):
            """Test opening a new session"""
            session_id = await session_manager.open_session()

            assert len(session_manager.sessions.keys()) == 1
            assert session_id in session_manager.sessions
            assert session_manager.sessions[session_id]["working_dir"] == "/home/user/workspace"

        @pytest.mark.asyncio
        async def test_close_session(self, session_manager, mock_session):
            """Test closing a session"""
            session_id = mock_session.session_id
            session_manager.sessions = {
                session_id: {
                    "session": mock_session,
                    "created_at": datetime.now(),
                    "working_dir": "/home/user/workspace"
                }
            }

            await session_manager.close_session(session_id)

            assert session_id not in session_manager.sessions
            mock_session.close.assert_called_once()

        @pytest.mark.asyncio
        async def test_close_nonexistent_session(self, session_manager):
            """Test closing a session that doesn't exist"""
            with pytest.raises(ValueError):
                await session_manager.close_session("nonexistent-session")

        @pytest.mark.asyncio
        async def test_run_command(self, session_manager, mock_session):
            """Test running a command in a session"""
            session_id = mock_session.session_id
            session_manager.sessions = {
                session_id: {
                    "session": mock_session,
                    "created_at": datetime.now(),
                    "working_dir": "/home/user/workspace"
                }
            }

            command = "echo hello"
            command_result = {
                "stdout": "hello\n",
                "stderr": "",
                "exit_code": 0,
                "new_working_directory": "/home/user/workspace/new",
                "unsuccessful": False
            }
            session_manager.command_executor.execute = AsyncMock(return_value=command_result)

            result = await session_manager.run_command(session_id, command)

            session_manager.command_executor.execute.assert_called_once_with(command, mock_session)
            assert session_manager.sessions[session_id]["working_dir"] == "/home/user/workspace/new"

            assert "stdout" in result
            assert "stderr" in result
            assert "exit_code" in result
            assert "new_working_directory" not in result
            assert "unsuccessful" not in result

        @pytest.mark.asyncio
        async def test_run_command_nonexistent_session(self, session_manager):
            """Test running a command in a nonexistent session"""
            with pytest.raises(ValueError):
                await session_manager.run_command("nonexistent-session", "echo hello")

        @pytest.mark.asyncio
        async def test_run_unsuccessful_command(self, session_manager, mock_session):
            """Test running a command that fails"""
            session_id = mock_session.session_id
            session_manager.sessions = {
                session_id: {
                    "session": mock_session,
                    "created_at": datetime.now(),
                    "working_dir": "/home/user/workspace"
                }
            }

            command = "invalid_command"
            command_result = {
                "stdout": "",
                "stderr": "command not found",
                "exit_code": 127,
                "new_working_directory": None,
                "unsuccessful": True
            }
            session_manager.command_executor.execute = AsyncMock(return_value=command_result)
            session_manager.close_session = AsyncMock()

            result = await session_manager.run_command(session_id, command)

            assert "stdout" in result
            assert "stderr" in result
            assert "exit_code" in result
