import asyncio
import logging
import os
import platform
import psutil
import shlex
import signal
import uuid
from typing import Any, Dict, Optional

class Session:
    """Represents a shell session"""

    def __init__(self, workspace_directory: str, session_id: Optional[str] = None):
        """Initialize the shell session

        Args:
            workspace_directory: Workspace directory
            session_id: The session ID
        """
        self.workspace_directory = workspace_directory
        self.session_id = session_id if session_id else str(uuid.uuid4().hex)
        self.process = None
        self.pgid = None
        self.system = platform.system()

        if self.system == "Windows":
            self.shell_command = "cmd.exe"
            self.line_ending = "\r\n"
        else:
            self.shell_command = os.environ.get("SHELL", "/bin/bash")
            self.line_ending = "\n"

        self.marker = None
        self.exit_code_marker = None
        self.full_command = None
        self.last_state = {
            "stdout": "",
            "stderr": "",
            "exit_code": None
        }

    async def open(self) -> Any:
        """Open a new shell session

        Returns:
            The shell session
        """
        if self.system == "Windows":
            self.process = await asyncio.create_subprocess_shell(
                self.shell_command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.workspace_directory
            )
            self.pgid = self.process.pid
        else:
            self.process = await asyncio.create_subprocess_shell(
                self.shell_command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.workspace_directory,
                start_new_session=True
            )
            self.pgid = os.getpgid(self.process.pid)

        await self._setup_shell_process()
        await self._drain_output()

        return self

    async def close(self) -> None:
        """Close the shell session

        This method is called when a session needs to be forcibly stopped,
        such as when it exceeds resource limits or timeouts.
        """
        if not self.process:
            return

        process_id = self.process.pid
        logging.info(f"Forcibly terminating session {self.session_id}")

        try:
            try:
                children = psutil.Process(process_id).children(recursive=True)
            except:
                children = []

            if self.system == "Windows":
                for child in reversed(children):
                    try:
                        child.kill()
                    except:
                        pass

                if self.process.returncode is None:  # Still running
                    self.process.kill()
            else:
                try:
                    if self.pgid:
                        os.killpg(self.pgid, signal.SIGKILL)
                except:
                    for child in children:
                        try:
                            child.kill()
                        except:
                            pass

                    if self.process.returncode is None:  # Still running
                        self.process.kill()
        except Exception as e:
            logging.error(f"Error forcibly terminating session {self.session_id}: {e}")

            try:
                self.process.kill()
            except:
                pass

        logging.info(f"Session {self.session_id} termination complete")

    async def execute_command(self, command: str) -> Dict[str, Any]:
        """Execute a command in this shell session

        Args:
            command: The command to execute

        Returns:
            Dict with stdout, stderr, exit_code
        """
        self._setup_markers_and_command(command)
        self.process.stdin.write(self.full_command.encode())
        await self.process.stdin.drain()
        await self._setup_stdout_output_and_exit_code()
        await self._setup_stderr_output()

        return self.last_state

    async def update_working_directory(self) -> str:
        """Update the stored working directory for a session

        Returns:
            The new working directory
        """
        marker = f"PWD_MARKER_{uuid.uuid4().hex}"
        if self.system == "Windows":
            # Windows 'cd' without args shows current dir
            cmd = f"cd{self.line_ending}echo {marker}{self.line_ending}"
        else:
            cmd = f"pwd; echo {marker}{self.line_ending}"
        pwd_output = []

        self.process.stdin.write(cmd.encode())
        await self.process.stdin.drain()

        while True:
            line = await self.process.stdout.readline()
            line_str = line.decode("utf-8", errors="replace").rstrip(self.line_ending)

            if line_str == marker:
                break

            pwd_output.append(line_str)

        if pwd_output:
            self.workspace_directory = pwd_output[-1]

        return self.workspace_directory

    async def get_resource_usage(self) -> Dict[str, float]:
        """Get CPU usage for this session (shell process and its children)

        Returns:
            CPU usage in percent
        """
        try:
            ps_process = psutil.Process(self.process.pid)
            cpu_percent = ps_process.cpu_percent(interval=None)
            memory_mb = ps_process.memory_info().rss / (1024 * 1024)

            try:
                children = ps_process.children(recursive=True)

                for child in children:
                    try:
                        cpu_percent += child.cpu_percent(interval=None)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass

                for child in children:
                    try:
                        memory_mb += child.memory_info().rss / (1024 * 1024)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass

            except Exception as e:
                logging.debug(f"Error getting child processes: {e}")

            return {
                "cpu_percent": cpu_percent,
                "memory_mb": memory_mb
            }
        except Exception as e:
            logging.error(f"Error getting resource usage: {e}")

        return {
            "cpu_percent": 0.0,
            "memory_mb": 0.0
        }

    async def _setup_shell_process(self) -> None:
        """Setup the shell process"""
        if self.system == "Windows":
            setup_commands = [
                f"set SHELL_ADAPTER_SESSION=1",
                f"set SHELL_ADAPTER_SESSION_ID={self.session_id}",
                f"prompt $$ ",  # Simple prompt for easier parsing
                f"cd /d {self.workspace_directory}"  # /d switch changes both drive and directory
            ]
        else:
            setup_commands = [
                "export SHELL_ADAPTER_SESSION=1",
                f"export SHELL_ADAPTER_SESSION_ID={self.session_id}",
                "export PS1='$ '",  # Simple prompt to make parsing easier
                "cd " + shlex.quote(self.workspace_directory),
            ]

        for cmd in setup_commands:
            self.process.stdin.write(f"{cmd}{self.line_ending}".encode())
            await self.process.stdin.drain()

    async def _drain_output(self) -> None:
        """Drain any pending output from a shell process"""
        init_marker = f"DRAIN_MARKER_{uuid.uuid4().hex}"

        self.process.stdin.write(f"echo {init_marker}{self.line_ending}".encode())
        await self.process.stdin.drain()

        # Drain stdout
        while True:
            line = await self.process.stdout.readline()
            if not line:  # Handle EOF
                break
            line_str = line.decode("utf-8", errors="replace").rstrip(self.line_ending)
            if line_str == init_marker:
                break

        # Drain stderr
        for _ in range(100):
            try:
                await asyncio.wait_for(self.process.stderr.readline(), 0.01)
            except asyncio.TimeoutError:
                break

    def _setup_markers_and_command(self, command: str) -> None:
        """Setup the command to execute"""
        self.marker = f"CMD_MARKER_{uuid.uuid4().hex}"
        self.exit_code_marker = f"EXIT_CODE_{uuid.uuid4().hex}"

        if self.system == "Windows":
            # Windows uses %ERRORLEVEL% and CRLF line endings
            self.full_command = (
                f"{command}\r\n"
                f"echo {self.exit_code_marker}%ERRORLEVEL%\r\n"
                f"echo {self.marker}\r\n"
            )
        else:
            # Unix uses $? and LF line endings
            self.full_command = (
                f"{command}\n"
                f"echo {self.exit_code_marker}$?\n"
                f"echo {self.marker}\n"
            )

    async def _setup_stdout_output_and_exit_code(self) -> None:
        """Get the stdout of the shell process"""
        stdout_data = []
        exit_code = 0

        while True:
            line = await self.process.stdout.readline()
            if not line:  # EOF
                break

            line_str = line.decode("utf-8", errors="replace").rstrip(self.line_ending)
            if line_str == self.marker:
                break
            elif line_str.startswith(self.exit_code_marker):
                try:
                    exit_code = int(line_str[len(self.exit_code_marker):])
                except ValueError:
                    logging.error(f"Failed to parse exit code")
                continue

            stdout_data.append(line_str)

        self.last_state["stdout"] = self.line_ending.join(stdout_data)
        self.last_state["exit_code"] = exit_code

    async def _setup_stderr_output(self) -> None:
        """Get the stderr of the shell process"""
        stderr_data = []
        for _ in range(100):
            try:
                stderr_line = await asyncio.wait_for(self.process.stderr.readline(), 0.01)
                if not stderr_line:
                    break
                stderr_data.append(stderr_line.decode("utf-8", errors="replace").rstrip(self.line_ending))
            except asyncio.TimeoutError:
                break

        self.last_state["stderr"] = self.line_ending.join(stderr_data)
