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
            "adapter_type": "telegram",
            "adapter_name": "test_bot",
            "bot_token": "test_bot_token",
            "api_id": "12345",
            "api_hash": "test_hash",
            "phone": "+1234567890",
            "retry_delay": 1,
            "connection_check_interval": 1,
            "flood_sleep_threshold": 10,
            "max_message_length": 20,
            "max_history_limit": 1,
            "max_pagination_iterations": 5
        },
        "attachments": {
            "storage_dir": "test_attachments",
            "max_age_days": 30,
            "max_total_attachments": 1000,
            "cleanup_interval_hours": 24,
            "max_file_size_mb": 1
        },
        "rate_limit": {
            "global_rpm": 30,
            "per_conversation_rpm": 60,
            "message_rpm": 60
        },
        "caching": {
            "max_messages_per_conversation": 100,
            "max_total_messages": 1000,
            "max_age_hours": 24,
            "cache_maintenance_interval": 3600,
            "cache_fetched_history": True
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
            "port": 8080
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
