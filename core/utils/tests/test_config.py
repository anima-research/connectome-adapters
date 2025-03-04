import os
import pytest
import yaml
import contextlib
from unittest.mock import patch, mock_open, MagicMock

from core.utils.config import Config

class TestConfig:
    """Tests for the Config class"""

    @pytest.fixture
    def default_config_data(self):
        """Default config data for testing"""
        return {
            "adapter": {
                "token": "test_token",
                "retry_delay": 5
            },
            "rate_limit": {
                "global_rpm": 10,
                "per_conversation_rpm": 3,
                "message_rpm": 3
            },
            "caching": {
                "max_total_messages": 1000,
                "max_age_hours": 24
            },
            "logging": {
                "level": "INFO"
            },
            "socketio": {
                "url": "http://localhost:5000",
                "port": 8080
            }
        }

    @pytest.fixture
    def config(self, default_config_data):
        """Create a Config instance with a mocked config file"""
        config_yaml = yaml.dump(default_config_data)
        with patch("builtins.open", mock_open(read_data=config_yaml)):
            with patch("os.path.exists", return_value=True):
                yield Config()

    class TestConfigLoading:
        """Tests for configuration loading functionality"""

        def test_load_config_with_existing_file(self, config, default_config_data):
            """Test loading configuration from an existing file"""
            config = config

            # Check that config categories were populated correctly
            for category in ["adapter", "rate_limit", "caching", "logging", "socketio"]:
                assert hasattr(config, category)
                assert getattr(config, category) == default_config_data[category]

    class TestConfigAccess:
        """Tests for configuration access methods"""

        @pytest.mark.parametrize("category,key,expected", [
            ("adapter", "token", "test_token"),
            ("adapter", "retry_delay", 5),
            ("logging", "level", "INFO"),
            ("socketio", "port", 8080),
        ])
        def test_get_setting_existing_keys(self, config, category, key, expected):
            """Test getting settings with existing keys"""
            config = config
            assert config.get_setting(category, key) == expected

        @pytest.mark.parametrize("category,key,default_value,expected", [
            ("adapter", "non_existent", "default_value", "default_value"),
            ("non_existent_category", "key", 42, 42),
        ])
        def test_get_setting_with_defaults(self, config, category, key, default_value, expected):
            """Test getting settings with default values"""
            config = config
            assert config.get_setting(category, key, default_value) == expected

        def test_get_setting_raises_error(self, config):
            """Test get_setting raises exception when key not found and no default"""
            config = config
            with pytest.raises(ValueError):
                config.get_setting("non_existent_category", "key")

        @pytest.mark.parametrize("category,key,expected", [
            ("adapter", "token", True),
            ("socketio", "port", True),
            ("adapter", "non_existent", False),
            ("non_existent_category", "key", False),
        ])
        def test_has_setting(self, config, category, key, expected):
            """Test has_setting method"""
            config = config
            assert config.has_setting(category, key) is expected

        def test_add_setting_success(self, config):
            """Test successfully adding a new setting"""
            assert not config.has_setting("adapter", "new_setting")

            config.add_setting("adapter", "new_setting", "new_value")

            assert config.has_setting("adapter", "new_setting")
            assert config.get_setting("adapter", "new_setting") == "new_value"

        def test_add_existing_setting_raises_error(self, config):
            """Test that adding an existing setting raises an error"""
            with pytest.raises(ValueError):
                config.add_setting("adapter", "token", "new_token")

        def test_add_setting_invalid_category_raises_error(self, config):
            """Test that adding a setting to an invalid category raises an error"""
            with pytest.raises(ValueError):
                config.add_setting("non_existent_category", "key", "value")