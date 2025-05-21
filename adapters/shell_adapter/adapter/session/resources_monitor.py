import asyncio
import logging
import psutil
import time

from typing import Optional
from adapters.shell_adapter.adapter.session.session import Session
from adapters.shell_adapter.adapter.session.event_emitter import EventEmitter
from core.utils.config import Config

class ResourceMonitor:
    """Monitors and limits resource usage for shell commands"""

    def __init__(self,
                 config: Config,
                 event_bus: EventEmitter,
                 maintenance_required: bool = False):
        """Initialize the resource monitor

        Args:
            config: Config instance
            event_bus: EventEmitter instance
            maintenance_required: Whether maintenance is required
        """
        self.config = config
        self.event_bus = event_bus
        self.maintenance_required = maintenance_required
        self.monitored_sessions = {}  # command_id -> session info
        self.running = False
        self.monitoring_task = None

        self.cpu_limit = self.config.get_setting("resources_monitoring", "cpu_percent_limit")
        self.memory_limit_mb = self.config.get_setting("resources_monitoring", "memory_mb_limit")
        self.disk_limit_mb = self.config.get_setting("resources_monitoring", "disk_mb_limit")
        self.check_interval = self.config.get_setting("resources_monitoring", "check_interval")
        self.workspace_directory = self.config.get_setting("adapter", "workspace_directory")

    async def start(self) -> None:
        """Start the resource monitoring"""
        self.running = True

        if self.maintenance_required:
            self.monitoring_task = asyncio.create_task(self._monitor_loop())

        logging.info("Resource monitor started")

    async def stop(self) -> None:
        """Stop the resource monitoring"""
        self.running = False

        if self.monitoring_task:
            self.monitoring_task.cancel()

        logging.info("Resource monitor stopped")

    def register_session(self,
                         command_id: str,
                         session: Session,
                         start_time: Optional[float] = None) -> None:
        """Register a session for monitoring

        Args:
            command_id: Unique ID for the command
            session: Session instance
            start_time: Start time (defaults to now)
        """
        if start_time is None:
            start_time = time.time()

        self.monitored_sessions[command_id] = {
            "session": session,
            "start_time": start_time
        }
        logging.debug(f"Registered session {session.session_id} for command {command_id}")

    def unregister_session(self, command_id):
        """Remove a session from monitoring

        Args:
            command_id: Command ID to unregister
        """
        if command_id in self.monitored_sessions:
            session_id = self.monitored_sessions[command_id]["session"].session_id
            del self.monitored_sessions[command_id]
            logging.debug(f"Unregistered session {session_id} for command {command_id}")

    async def _monitor_loop(self):
        """Main monitoring loop"""
        while self.running:
            try:
                await asyncio.sleep(self.check_interval)
                await self._check_sessions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Error in resource monitoring loop: {e}", exc_info=True)

    async def _check_sessions(self):
        """Check all monitored sessions against resource limits"""
        command_ids = list(self.monitored_sessions.keys())

        for command_id in command_ids:
            if command_id not in self.monitored_sessions:
                continue

            session = self.monitored_sessions[command_id]["session"]

            try:
                resources = await session.get_resource_usage()

                if resources["cpu_percent"] > self.cpu_limit:
                    await self._terminate_command(
                        command_id,
                        f"CPU usage {resources['cpu_percent']:.1f} exceeded limit"
                    )
                    continue

                if resources["memory_mb"] > self.memory_limit_mb:
                    await self._terminate_command(
                        command_id,
                        f"Memory usage {resources['memory_mb']:.1f}MBexceeded limit"
                    )
                    continue

            except Exception as e:
                logging.error(f"Error monitoring session: {e}")
                self.unregister_session(command_id)

    async def _terminate_command(self, command_id, reason):
        """Terminate a command that exceeded resource limits

        Args:
            command_id: Command ID to terminate
            reason: Reason for termination
        """
        logging.warning(f"Terminating command {command_id}: {reason}")
        await self.event_bus.emit("command_terminated", command_id=command_id)
        self.unregister_session(command_id)
