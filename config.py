# config.py
import os
import yaml
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("Config")

class Config:
    _instance = None

    def __new__(cls, config_path: str = "config.yaml"):
        if cls._instance is None:
            cls._instance = super(Config, cls).__new__(cls)
            cls._instance.initialize(config_path)
        return cls._instance

    def initialize(self, config_path: str):
        """Initialize the singleton instance"""
        self.config_path = config_path
        self.token = None
        self.settings = {}
        self.load_config()

    def load_config(self) -> bool:
        """Load configuration from YAML file"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as file:
                    config = yaml.safe_load(file) or {}
                    self.token = config.get("token")

                    if "settings" in config and isinstance(config["settings"], dict):
                        self.settings = config["settings"]

                if not self.token:
                    logger.error("Token not found in config file")
                    return

                logger.info("Loaded configuration")
            else:
                logger.error("Config file not found")
        except Exception as e:
            logger.error(f"Error loading config: {str(e)}")

    def get_token(self) -> str:
        """Get the bot token"""
        if not self.token:
            raise ValueError("Bot token not available in configuration")
        return self.token

    def get_setting(self, key: str, default=None):
        """Get a specific setting with support for nested keys (e.g., 'privacy.retention_days')"""
        try:
            if '.' in key:
                parts = key.split('.')
                current = self.settings
                for part in parts:
                    if not isinstance(current, dict) or part not in current:
                        return default
                    current = current[part]
                return current
            return self.settings.get(key, default)
        except (KeyError, AttributeError):
            if default is not None:
                return default
            raise ValueError(f"Setting '{key}' not found in configuration")

    def has_setting(self, key: str) -> bool:
        """Check if a setting exists, with support for nested keys"""
        try:
            if '.' in key:
                parts = key.split('.')
                current = self.settings
                for part in parts:
                    if not isinstance(current, dict) or part not in current:
                        return False
                    current = current[part]
                return True
            return key in self.settings
        except (KeyError, AttributeError):
            return False

    @classmethod
    def get_instance(cls) -> 'Config':
        """Get the singleton instance, creating it if necessary"""
        if cls._instance is None:
            return cls()
        return cls._instance
