import asyncio
import logging
import os
import signal
import shlex
import subprocess
import time
import uuid

from datetime import datetime
from typing import Any, Dict, Tuple

from adapters.shell_adapter.adapter.session.event_emitter import EventEmitter
from adapters.shell_adapter.adapter.session.resources_monitor import ResourceMonitor
from adapters.shell_adapter.adapter.session.session import Session
from core.utils.config import Config

class CommandExecutor:
    """Executes commands in shell sessions and processes their output"""

    def __init__(self,
                 config: Config,
                 event_bus: EventEmitter,
                 resource_monitor: ResourceMonitor,
                 maintenance_required: bool = False):
        """Initialize the command executor

        Args:
            config: Config instance
            event_bus: EventEmitter instance
            resource_monitor: ResourceMonitor instance
            maintenance_required: Whether maintenance is required
        """
        self.config = config
        self.event_bus = event_bus
        self.resource_monitor = resource_monitor
        self.maintenance_required = maintenance_required
        self.running = False
        self.command_tasks = {}  # Track running commands: {command_id: {task, start_time, session}}
        self.monitoring_task = None
        self.workspace_directory = self.config.get_setting("adapter", "workspace_directory")
        self.max_output_size = self.config.get_setting("output", "max_output_size")
        self.begin_output_size = self.config.get_setting("output", "begin_output_size")
        self.end_output_size = self.config.get_setting("output", "end_output_size")
        self.command_max_lifetime = self.config.get_setting("adapter", "command_max_lifetime")

        self.event_bus.on("command_terminated", self._cancel_command)

    async def start(self):
        """Start the command executor and monitoring task"""
        self.running = True

        if self.maintenance_required:
            self.monitoring_task = asyncio.create_task(self._monitor_commands())

        logging.info("Command executor started")

    async def stop(self):
        """Stop the command executor and cancel all running commands"""
        self.running = False

        if self.monitoring_task:
            self.monitoring_task.cancel()

        command_ids = list(self.command_tasks.keys())
        for command_id in command_ids:
            try:
                await self._cancel_command(command_id)
            except Exception as e:
                logging.error(f"Error canceling command {command_id}: {e}")

        logging.info("Command executor stopped")

    async def execute(self, command: str, session: Session) -> Dict[str, Any]:
        """Execute a command either in a session or independently

        Args:
            command: The command to execute
            session: The session to execute the command in

        Returns:
            Dict containing stdout, stderr, and exit code
        """
        command_id = str(uuid.uuid4())
        self.command_tasks[command_id] = {
            "command": command,
            "session": session,
            "task": asyncio.create_task(session.execute_command(command)),
            "start_time": datetime.now()
        }
        result = {
            "stdout": "",
            "stderr": "Command execution was cancelled (timeout or shutdown)",
            "exit_code": -1
        }

        logging.debug(f"Executing command: {command}")
        self.resource_monitor.register_session(command_id, session)

        try:
            result = await self.command_tasks[command_id]["task"]
        except Exception as e:
            logging.error(f"Error executing command: {e}")

        self.resource_monitor.unregister_session(command_id)

        if session:
            await self.event_bus.emit(
                "directory_updated",
                session_id=session.session_id,
                working_dir=await session.update_working_directory()
            )

        if command_id in self.command_tasks:
            del self.command_tasks[command_id]

        return self._format_output(result)

    def _format_output(self, cmd_result: Dict[str, Any]) -> Dict[str, Any]:
        """Format command output and apply truncation if needed

        Args:
            cmd_result: Dict containing stdout, stderr, and exit code

        Returns:
            Dict containing formatted output
        """
        stdout, stdout_size = self._truncate_text(cmd_result["stdout"])
        stderr, stderr_size = self._truncate_text(cmd_result["stderr"])

        return {
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": cmd_result["exit_code"],
            "original_stdout_size": stdout_size,
            "original_stderr_size": stderr_size
        }

    def _truncate_text(self, text: str) -> Tuple[str, int]:
        """Truncate text to a maximum size

        Args:
            text: The text to truncate

        Returns:
            Tuple containing
              - the truncated text
              - the original size if truncation is needed, otherwise None
        """
        original_size = len(text)
        need_truncation = original_size > self.max_output_size

        if need_truncation:
            middle_text = f"\n...[Output truncated]...\n"
            text = text[:self.begin_output_size] + middle_text + text[-self.end_output_size:]

        return text, original_size if need_truncation else None

    async def _monitor_commands(self) -> None:
        """Periodically check for long-running commands and cancel them if they exceed the timeout"""
        check_interval = 30  # Check every 30 seconds

        while self.running:
            try:
                await asyncio.sleep(check_interval)

                now = datetime.now()
                command_ids = list(self.command_tasks.keys())

                for command_id in command_ids:
                    if command_id not in self.command_tasks:
                        continue  # Command might have completed during iteration

                    command_info = self.command_tasks[command_id]
                    duration = now - command_info["start_time"]

                    if duration.total_seconds() > self.command_max_lifetime:
                        command = command_info["command"]
                        logging.warning(f"Command timeout exceeded: '{command}' and will be stopped")
                        await self._cancel_command(command_id)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Error in command monitoring: {e}", exc_info=True)

    async def _cancel_command(self, command_id: str) -> None:
        """Cancel a running command

        Args:
            command_id: ID of the command to cancel
        """
        if command_id not in self.command_tasks:
            return

        command_info = self.command_tasks[command_id]
        command_info["task"].cancel()

        if command_info["session"]:
            await self.event_bus.emit(
                "session_terminated",
                session_id=command_info["session"].session_id
            )

        del self.command_tasks[command_id]
