import asyncio
import logging
import time
import uuid

from datetime import datetime, timedelta
from typing import Any, Dict

from adapters.shell_adapter.adapter.session.command_executor import CommandExecutor
from adapters.shell_adapter.adapter.session.event_emitter import EventEmitter
from adapters.shell_adapter.adapter.session.resources_monitor import ResourceMonitor
from adapters.shell_adapter.adapter.session.session import Session

from core.utils.config import Config

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
        self.command_executor = None
        self.resource_monitor = None
        self.event_bus = None
        self.session_max_lifetime = self.config.get_setting("adapter", "session_max_lifetime")
        self.workspace_directory = self.config.get_setting("adapter", "workspace_directory")

    async def start(self) -> None:
        """Start the session manager and cleanup task"""
        self.running = True

        self.event_bus = EventEmitter()
        self.event_bus.on("session_terminated", self.close_session)
        self.event_bus.on("directory_updated", self._update_session_directory)

        self.resource_monitor = ResourceMonitor(
            self.config, self.event_bus, self.maintenance_required
        )
        await self.resource_monitor.start()

        self.command_executor = CommandExecutor(
            self.config, self.event_bus, self.resource_monitor, self.maintenance_required
        )
        await self.command_executor.start()

        if self.maintenance_required:
            self.cleanup_task = asyncio.create_task(self._cleanup_sessions())

        logging.info("Session manager started")

    async def stop(self) -> None:
        """Stop the session manager and close all sessions"""
        self.running = False

        if self.resource_monitor:
            await self.resource_monitor.stop()

        if self.command_executor:
            await self.command_executor.stop()

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

        return await self.command_executor.execute(
            command, self.sessions[session_id]["session"]
        )

    async def close_session(self, session_id: str) -> None:
        """Close a shell session

        Args:
            session_id: The ID of the session to close
        """
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found; it might have been closed already.")

        logging.info(f"Closing session {session_id}")

        await self.sessions[session_id]["session"].close()
        del self.sessions[session_id]

        logging.info(f"Session {session_id} closed")

    async def _cleanup_sessions(self) -> None:
        """Periodically check and clean up idle or expired sessions"""
        cleanup_interval = 180  # Check every 3 minutes

        while self.running:
            try:
                await asyncio.sleep(cleanup_interval)

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

                    lifetime = now - session["created_at"]
                    if lifetime > timedelta(hours=self.session_max_lifetime):
                        logging.info(f"Session {session_id} exceeded max lifetime, closing")
                        await self.close_session(session_id)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Error in session cleanup: {e}", exc_info=True)

    def _update_session_directory(self, session_id: str, new_directory: str) -> None:
        """Update the working directory for a session

        Args:
            session_id: The ID of the session to update
            new_directory: The new working directory
        """
        if session_id in self.sessions:
            self.sessions[session_id]["working_dir"] = new_directory
