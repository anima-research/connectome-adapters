import os
import sys
import pytest
import yaml
from unittest.mock import patch, mock_open

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.utils.config import Config

@pytest.fixture
def default_config_data():
    """Default config data available to all tests"""
    return {
        "adapter": {
            "adapter_type": "slack",
            "adapter_name": "slack_bot",
            "adapter_id": "slack_bot_id",
            "bot_token": "bot_token",
            "app_token": "app_token",
            "retry_delay": 5,
            "connection_check_interval": 300,
            "max_reconnect_attempts": 5,
            "max_message_length": 100,
            "max_history_limit": 10,
            "max_pagination_iterations": 1
        },
        "attachments": {
            "storage_dir": "test_attachments",
            "max_age_days": 30,
            "max_total_attachments": 1000,
            "cleanup_interval_hours": 24,
            "max_file_size_mb": 8,
            "max_attachments_per_message": 1
        },
        "caching": {
            "max_messages_per_conversation": 100,
            "max_total_messages": 1000,
            "max_age_hours": 24,
            "cache_maintenance_interval": 3600,
            "cache_fetched_history": True
        },
        "rate_limit": {
            "global_rpm": 120,
            "per_conversation_rpm": 60,
            "message_rpm": 60
        },
        "logging": {
            "logging_level": "INFO",
            "log_format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            "log_file_path": "test.log",
            "max_log_size": 1024,
            "backup_count": 3
        },
        "socketio": {
            "url": "http://localhost:5000",
            "port": 8085
        }
    }

@pytest.fixture
def mocked_config(default_config_data):
    """Create a mocked Config instance with test data"""
    with patch("builtins.open", mock_open(read_data=yaml.dump(default_config_data))):
        with patch("os.path.exists", return_value=True):
            yield Config()

@pytest.fixture
def patch_config(mocked_config):
    """Patch the Config class to use our mocked instance in all tests"""
    with patch("core.utils.config.Config", return_value=mocked_config):
        yield mocked_config
