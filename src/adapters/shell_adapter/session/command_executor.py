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

from src.adapters.shell_adapter.session.session import Session
from src.core.utils.config import Config

class CommandExecutor:
    """Executes commands in shell sessions and processes their output"""

    def __init__(self, config: Config):
        """Initialize the command executor

        Args:
            config: Config instance
            resource_monitor: ResourceMonitor instance
        """
        self.config = config
        self.command_tasks = {}  # Track running commands: {command_id: {task, start_time, session}}
        self.workspace_directory = self.config.get_setting("adapter", "workspace_directory")
        self.max_output_size = self.config.get_setting("adapter", "max_output_size")
        self.begin_output_size = self.config.get_setting("adapter", "begin_output_size")
        self.end_output_size = self.config.get_setting("adapter", "end_output_size")
        self.command_max_lifetime = self.config.get_setting("adapter", "command_max_lifetime")
        self.cpu_limit = self.config.get_setting("adapter", "cpu_percent_limit")
        self.memory_limit_mb = self.config.get_setting("adapter", "memory_mb_limit")

    def __del__(self):
        """Stop the command executor and cancel all running commands"""
        command_ids = list(self.command_tasks.keys())

        for command_id in command_ids:
            try:
                self.command_tasks[command_id]["task"].cancel()
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logging.error(f"Error canceling command {command_id} during cleanup: {e}")

    async def execute(self, command: str, session: Session) -> Dict[str, Any]:
        """Execute a command with non-blocking resource monitoring

        Args:
            command: The command to execute
            session: The session to execute the command in

        Returns:
            Dict containing stdout, stderr, and exit code
        """
        command_id = str(uuid.uuid4())
        execution_task = asyncio.create_task(session.execute_command(command))
        monitoring_task = asyncio.create_task(self._monitor_command_resources(command_id, execution_task, session))

        self.command_tasks[command_id] = {
            "command": command,
            "session": session,
            "task": execution_task,
            "monitoring_task": monitoring_task
        }
        result = {
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "unsuccessful": False,
            "new_working_directory": None
        }

        logging.info(f"Starting execution of command {command} with ID {command_id}")

        try:
            result = await execution_task
            logging.info(f"Command {command_id} completed successfully")
        except asyncio.CancelledError:
            result["unsuccessful"] = True
            logging.info(f"Command {command_id} was cancelled")
        except Exception as e:
            result["unsuccessful"] = True
            logging.error(f"Error executing command {command_id}: {e}", exc_info=True)
        finally:
            if not monitoring_task.done():
                monitoring_task.cancel()
            if command_id in self.command_tasks:
                del self.command_tasks[command_id]

        if session:
            result["new_working_directory"] = await session.update_working_directory()

        return self._format_output(result)

    async def _monitor_command_resources(self,
                                         command_id: str,
                                         execution_task: asyncio.Task,
                                         session: Session) -> None:
        """Monitor command resources in a separate task

        Args:
            command_id: Unique ID for the command
            execution_task: The task executing the command
            session: The session running the command
        """
        start_time = datetime.now()

        try:
            while not execution_task.done():
                current_time = datetime.now()
                duration = (current_time - start_time).total_seconds()

                if duration > self.command_max_lifetime:
                    logging.warning(f"Command timeout exceeded; '{command_id}' will be stopped")
                    execution_task.cancel()
                    break

                if session:
                    resources = await session.get_resource_usage()
                    termination_required = False

                    if resources["cpu_percent"] > self.cpu_limit:
                        logging.warning(f"Command {command_id} exceeded CPU limit")
                        termination_required = True

                    if resources["memory_mb"] > self.memory_limit_mb:
                        logging.warning(f"Command {command_id} exceeded memory limit")
                        termination_required = True

                    if termination_required:
                        execution_task.cancel()
                        break

                await asyncio.sleep(10)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logging.error(f"Error in resource monitoring for command {command_id}: {e}", exc_info=True)

    def _format_output(self, cmd_result: Dict[str, Any]) -> Dict[str, Any]:
        """Format command output and apply truncation if needed

        Args:
            cmd_result: Dict containing stdout, stderr, and exit code

        Returns:
            Dict containing formatted output
        """
        stdout, stdout_size = self._truncate_text(cmd_result.get("stdout", ""))
        stderr, stderr_size = self._truncate_text(cmd_result.get("stderr", ""))

        result = {
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": cmd_result["exit_code"],
            "original_stdout_size": stdout_size,
            "original_stderr_size": stderr_size,
            "new_working_directory": cmd_result.get("new_working_directory", None),
            "unsuccessful": cmd_result.get("unsuccessful", False)
        }

        return result

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
