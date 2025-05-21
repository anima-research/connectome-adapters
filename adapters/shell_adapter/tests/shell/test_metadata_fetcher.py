import os
import platform
import pytest
import sys
import subprocess

from unittest.mock import MagicMock, patch
from adapters.shell_adapter.adapter.shell.metadata_fetcher import MetadataFetcher

class TestMetadataFetcher:
    """Tests for the Shell Metadata Fetcher class"""

    @pytest.fixture
    def mock_config(self):
        """Create a mock config for testing"""
        config = MagicMock()
        config.get_setting.side_effect = lambda section, key: {
            ("adapter", "workspace_directory"): "/home/user/workspace"
        }.get((section, key))
        return config

    @pytest.fixture
    def metadata_fetcher(self, mock_config):
        """Create a ShellMetadataFetcher with mocked dependencies"""
        return MetadataFetcher(mock_config)

    class TestInitialization:
        """Tests for the initialization process"""

        def test_initialization(self, mock_config):
            """Test that the fetcher initializes properly"""
            with patch.object(MetadataFetcher, "_collect_metadata") as mock_collect:
                fetcher = MetadataFetcher(mock_config)

                assert fetcher.config == mock_config
                assert "operating_system" in fetcher.metadata
                assert "shell" in fetcher.metadata
                assert "workspace_directory" in fetcher.metadata
                assert fetcher.metadata["workspace_directory"] == "/home/user/workspace"
                mock_collect.assert_called_once()

    class TestOperatingSystemInfo:
        """Tests for operating system information collection"""

        def test_linux_os_info(self, mock_config):
            """Test Linux OS information collection"""
            with patch("platform.system", return_value="Linux"), \
                 patch("platform.freedesktop_os_release", return_value={
                     "NAME": "Ubuntu",
                     "PRETTY_NAME": "Ubuntu 22.04.2 LTS"
                 }), \
                 patch.object(MetadataFetcher, "_setup_shell_info"):

                fetcher = MetadataFetcher(mock_config)
                assert "Ubuntu" in fetcher.metadata["operating_system"]
                assert "22.04.2" in fetcher.metadata["operating_system"]

        def test_linux_os_info_fallback(self, mock_config):
            """Test Linux OS information fallback when freedesktop_os_release is not available"""
            with patch("platform.system", return_value="Linux"), \
                patch("builtins.hasattr", return_value=False), \
                patch("platform.version", return_value="5.15.0-78-generic"), \
                patch.object(MetadataFetcher, "_setup_shell_info"):

                fetcher = MetadataFetcher(mock_config)
                assert "Linux" in fetcher.metadata["operating_system"]
                assert "5.15.0-78-generic" in fetcher.metadata["operating_system"]

        def test_macos_os_info(self, mock_config):
            """Test macOS information collection"""
            with patch("platform.system", return_value="Darwin"), \
                 patch("platform.mac_ver", return_value=("12.6.3", "", "")), \
                 patch.object(MetadataFetcher, "_setup_shell_info"):

                fetcher = MetadataFetcher(mock_config)
                assert "macOS" in fetcher.metadata["operating_system"]
                assert "12.6.3" in fetcher.metadata["operating_system"]

        def test_windows_os_info(self, mock_config):
            """Test Windows information collection"""
            with patch("platform.system", return_value="Windows"), \
                 patch("platform.version", return_value="10.0.19045"), \
                 patch.object(MetadataFetcher, "_setup_shell_info"):

                fetcher = MetadataFetcher(mock_config)
                assert "Windows" in fetcher.metadata["operating_system"]
                assert "10.0.19045" in fetcher.metadata["operating_system"]

    class TestShellInfo:
        """Tests for shell information collection"""

        def test_bash_shell_info(self, mock_config):
            """Test Bash shell information collection"""
            with patch("platform.system", return_value="Linux"), \
                 patch("os.environ.get", return_value="/bin/bash"), \
                 patch("os.path.basename", return_value="bash"), \
                 patch("subprocess.check_output", return_value="GNU bash, version 5.1.16"), \
                 patch.object(MetadataFetcher, "_setup_operating_system_info"):

                fetcher = MetadataFetcher(mock_config)
                assert "bash" in fetcher.metadata["shell"]
                assert "5.1.16" in fetcher.metadata["shell"]

        def test_powershell_info(self, mock_config):
            """Test PowerShell information collection"""
            with patch("platform.system", return_value="Windows"), \
                 patch("shutil.which", return_value=r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"), \
                 patch("subprocess.check_output", return_value="PowerShell 5.1.19041.3031"), \
                 patch.object(MetadataFetcher, "_setup_operating_system_info"):

                fetcher = MetadataFetcher(mock_config)
                assert "PowerShell" in fetcher.metadata["shell"]
                assert "5.1" in fetcher.metadata["shell"]

        def test_cmd_info(self, mock_config):
            """Test CMD information collection"""
            with patch("platform.system", return_value="Windows"), \
                 patch("shutil.which", return_value=None), \
                 patch.object(MetadataFetcher, "_setup_operating_system_info"):

                fetcher = MetadataFetcher(mock_config)
                assert "cmd.exe" in fetcher.metadata["shell"]

    class TestFetch:
        """Tests for the fetch method"""

        def test_fetch_returns_metadata(self, metadata_fetcher):
            """Test that fetch returns the metadata"""
            # Setup some test metadata
            metadata_fetcher.metadata = {
                "operating_system": "Test OS 1.0",
                "shell": "test_shell 2.0",
                "root_directory": "/test/dir"
            }

            result = metadata_fetcher.fetch()

            assert result == metadata_fetcher.metadata
            assert result["operating_system"] == "Test OS 1.0"
            assert result["shell"] == "test_shell 2.0"
            assert result["root_directory"] == "/test/dir"
