import asyncio
import logging
import time
import uuid

from datetime import datetime, timedelta
from typing import Any, Dict

from src.adapters.shell_adapter.session.command_executor import CommandExecutor
from src.adapters.shell_adapter.session.session import Session

from src.core.utils.config import Config

class Manager:
    """Manages shell sessions with lifecycle handling and cleanup"""

    def __init__(self, config: Config, maintenance_required: bool = False):
        """Initialize the session manager

        Args:
            config: Config instance
            maintenance_required: Whether maintenance is required
        """
        self.config = config
        self.maintenance_required = maintenance_required
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.cleanup_task = None
        self.running = False
        self.command_executor = CommandExecutor(self.config)
        self.sessions_with_running_commands = set()
        self.session_max_lifetime = self.config.get_setting("adapter", "session_max_lifetime")
        self.workspace_directory = self.config.get_setting("adapter", "workspace_directory")

    async def start(self) -> None:
        """Start the session manager and cleanup task"""
        self.running = True

        if self.maintenance_required:
            self.cleanup_task = asyncio.create_task(self._cleanup_sessions())

        logging.info("Session manager started")

    async def stop(self) -> None:
        """Stop the session manager and close all sessions"""
        self.running = False

        if self.cleanup_task:
            self.cleanup_task.cancel()

        session_ids = list(self.sessions.keys())
        for session_id in session_ids:
            try:
                await self.close_session(session_id)
            except Exception as e:
                logging.error(f"Error closing session {session_id}: {e}")

        logging.info("Session manager stopped")

    async def open_session(self) -> str:
        """Create a new shell session

        Returns:
            str: The ID of the new session
        """
        session_id = str(uuid.uuid4())

        self.sessions[session_id] = {
            "session": await Session(self.workspace_directory, session_id).open(),
            "created_at": datetime.now(),
            "working_dir": self.workspace_directory
        }

        logging.info(f"Created new session {session_id}")
        return session_id

    async def run_command(self, session_id: str, command: str) -> Dict[str, Any]:
        """Execute a command in a shell session

        Args:
            session_id: The ID of the session to execute the command in
            command: The command to execute

        Returns:
            Dict[str, Any]: The result of the command
        """
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found. Command execution failed.")

        self.sessions_with_running_commands.add(session_id)

        cmd_result = await self.command_executor.execute(
            command, self.sessions[session_id]["session"]
        )

        if cmd_result["new_working_directory"]:
            self.sessions[session_id]["working_dir"] = cmd_result["new_working_directory"]
        del cmd_result["new_working_directory"]

        if cmd_result["unsuccessful"]:
            await self.close_session(session_id)
        del cmd_result["unsuccessful"]

        self.sessions_with_running_commands.discard(session_id)

        return cmd_result

    async def close_session(self, session_id: str) -> None:
        """Close a shell session

        Args:
            session_id: The ID of the session to close
        """
        if session_id not in self.sessions:
            raise ValueError(
                f"Session {session_id} not found."\
                "It might have been closed already (due to timeout or other reasons)."
            )

        logging.info(f"Closing session {session_id}")

        await self.sessions[session_id]["session"].close()
        del self.sessions[session_id]

        logging.info(f"Session {session_id} closed")

    async def _cleanup_sessions(self) -> None:
        """Periodically check and clean up idle or expired sessions"""
        while self.running:
            try:
                await asyncio.sleep(30)

                now = datetime.now()
                session_ids = list(self.sessions.keys())

                for session_id in session_ids:
                    if session_id not in self.sessions:
                        continue  # Session might have been closed during iteration

                    session = self.sessions[session_id]

                    if session["session"].process.returncode is not None:
                        logging.info(f"Session {session_id} process exited, cleaning up")
                        await self.close_session(session_id)
                        continue

                    if session_id in self.sessions_with_running_commands:
                        continue

                    lifetime = now - session["created_at"]
                    if lifetime > timedelta(minutes=self.session_max_lifetime):
                        logging.info(f"Session {session_id} exceeded max lifetime, closing")
                        await self.close_session(session_id)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Error in session cleanup: {e}", exc_info=True)
