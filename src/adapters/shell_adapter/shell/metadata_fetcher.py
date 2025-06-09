import logging
import os
import platform
import shutil
import subprocess
from typing import Any, Dict

class MetadataFetcher:
    """Fetches metadata about the shell environment"""

    def __init__(self, config):
        """Initialize the metadata provider

        Args:
            config: The adapter configuration
        """
        self.config = config
        self.metadata = {
            "operating_system": "",
            "shell": "",
            "workspace_directory": self.config.get_setting("adapter", "workspace_directory")
        }

        self._collect_metadata()

    def _collect_metadata(self) -> None:
        """Collect metadata about the shell environment"""
        try:
            self._setup_operating_system_info()
            self._setup_shell_info()
        except Exception as e:
            logging.error(f"Error collecting shell metadata: {e}", exc_info=True)

    def _setup_operating_system_info(self) -> None:
        """Setup the operating system information"""
        system = platform.system()

        os_name = system
        os_version = ""

        if system == "Linux" and hasattr(platform, "freedesktop_os_release"):
            os_release = platform.freedesktop_os_release()
            os_name = os_release.get("NAME", "Linux")
            os_version = os_release.get("PRETTY_NAME", platform.version())
        elif system == "Darwin":
            os_name = "macOS"
            os_version = platform.mac_ver()[0]

        if not os_version:
            os_version = platform.version()

        self.metadata["operating_system"] = f"{os_name} {os_version}".strip()

    def _setup_shell_info(self) -> None:
        """Setup the shell information"""
        system = platform.system()
        shell_version = ""
        shell_type = ""

        if system in ["Linux", "Darwin"]:
            shell_path = os.environ.get("SHELL", "")
            shell_type = os.path.basename(shell_path) if shell_path else "unknown"

            try:
                version_output = subprocess.check_output(
                    [shell_path, "--version"],
                    stderr=subprocess.STDOUT,
                    text=True
                )
                shell_version = version_output.split('\n')[0]
            except:
                shell_version = ""
        elif system == "Windows":
            if shutil.which("powershell.exe") is not None:
                shell_type = "PowerShell"
                try:
                    version_output = subprocess.check_output(
                        ["powershell.exe", "-Command", "$PSVersionTable.PSVersion"],
                        stderr=subprocess.STDOUT,
                        text=True
                    )
                    shell_version = version_output.strip()
                except:
                    shell_version = ""
            else:
                shell_type = "cmd.exe"
                shell_version = ""

        self.metadata["shell"] = f"{shell_type} {shell_version}".strip()

    def fetch(self) -> Dict[str, Any]:
        """Get the shell metadata

        Returns:
            Dictionary containing shell metadata
        """
        return self.metadata
