import copy
import json
import os
import pytest
import shutil
import sys
import yaml

from unittest.mock import AsyncMock, MagicMock, mock_open, patch
from pathlib import Path

project_root = os.path.abspath(os.path.dirname(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.core.cache.cache import Cache
from src.core.utils.config import Config

@pytest.fixture
def basic_config_data():
    """Base configuration data that all adapter configs will extend"""
    return {
        "adapter": {
            "adapter_name": "test_bot",
            "adapter_id": "test_bot_id",
            "retry_delay": 5,
            "connection_check_interval": 1,
            "max_message_length": 100,
            "max_reconnect_attempts": 5,
            "max_history_limit": 10,
            "max_pagination_iterations": 5
        },
        "attachments": {
            "storage_dir": "test_attachments",
            "max_age_days": 30,
            "max_total_attachments": 1000,
            "cleanup_interval_hours": 24,
            "max_file_size_mb": 8,
            "max_attachments_per_message": 1
        },
        "rate_limit": {
            "global_rpm": 120,
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
            "url": "http://localhost:3000",
            "port": 8081
        }
    }

@pytest.fixture
def mock_config_factory():
    """Factory fixture to create Config mocks with specified data"""
    def _create_config(config_data):
        with patch("builtins.open", mock_open(read_data=yaml.dump(config_data))):
            with patch("os.path.exists", return_value=True):
                return Config()
    return _create_config

@pytest.fixture
def discord_config(basic_config_data, mock_config_factory):
    """Mocked Config instance for Discord tests"""
    config = copy.deepcopy(basic_config_data)
    config["adapter"].update({
        "adapter_type": "discord",
        "bot_token": "bot_token",
        "application_id": "123456789"
    })
    return mock_config_factory(config)

@pytest.fixture
def discord_webhook_config(basic_config_data, mock_config_factory):
    """Mocked Config instance for Discord webhook tests"""
    config = copy.deepcopy(basic_config_data)
    config["attachments"] = {
        "storage_dir": "test_attachments",
        "max_file_size_mb": 8,
        "max_attachments_per_message": 1
    }
    config["adapter"].update({
        "adapter_type": "discord_webhook",
        "bot_token": "bot_token",
        "application_id": "123456789",
        "webhooks": [
            {
                "conversation_id": "123/456",
                "url": "https://discord.com/api/webhooks/123/456",
                "name": "test_webhook"
            }
        ]
    })
    return mock_config_factory(config)

@pytest.fixture
def slack_config(basic_config_data, mock_config_factory):
    """Mocked Config instance for Slack tests"""
    config = copy.deepcopy(basic_config_data)
    config["adapter"].update({
        "adapter_type": "slack",
        "bot_token": "bot_token",
        "app_token": "app_token",
    })
    return mock_config_factory(config)

@pytest.fixture
def telegram_config(basic_config_data, mock_config_factory):
    """Mocked Config instance for Telegram tests"""
    config = copy.deepcopy(basic_config_data)
    config["adapter"].update({
        "adapter_type": "telegram",
        "bot_token": "test_bot_token",
        "api_id": "12345",
        "api_hash": "test_hash",
        "phone": "+1234567890",
        "flood_sleep_threshold": 10,
        "max_history_limit": 1
    })
    return mock_config_factory(config)

@pytest.fixture
def zulip_config(basic_config_data, mock_config_factory):
    """Mocked Config instance for Zulip tests"""
    config = copy.deepcopy(basic_config_data)
    config["adapter"].update({
        "adapter_type": "zulip",
        "adapter_id": "789",
        "zuliprc_path": "config/zuliprc",
        "adapter_email": "adapter_email@example.com",
        "site": "https://zulip.example.com/",
        "chunk_size": 8192,
        "emoji_mappings": "config/zulip_emoji_mappings.csv"
    })
    return mock_config_factory(config)

@pytest.fixture(scope="session", autouse=True)
def ensure_test_directories():
    """Create necessary test directories before any tests and clean up after all tests"""
    print("\nSetting up test directories...")

    os.makedirs("test_attachments", exist_ok=True)
    os.makedirs("test_attachments/document", exist_ok=True)
    os.makedirs("test_attachments/image", exist_ok=True)
    os.makedirs("test_attachments/tmp_uploads", exist_ok=True)

    yield

    print("\nCleaning up test directories...")

    if os.path.exists("test_attachments"):
        shutil.rmtree("test_attachments")

@pytest.fixture(scope="function", autouse=True)
def cache_mock(basic_config_data, mock_config_factory):
    """Fixture to create and tear down a Cache singleton for tests.

    This fixture has module scope, meaning it will be created once per test file
    and torn down at the end of all tests in that file.
    """
    original_instance = Cache._instance
    Cache._instance = None
    cache_instance = Cache.get_instance(
        config=mock_config_factory(basic_config_data),
        start_maintenance=False
    )

    yield cache_instance

    Cache._instance = original_instance

@pytest.fixture
def rate_limiter_mock():
    """Create a mock rate limiter"""
    rate_limiter = AsyncMock()
    rate_limiter.limit_request = AsyncMock(return_value=None)
    rate_limiter.get_wait_time = AsyncMock(return_value=0)
    return rate_limiter
