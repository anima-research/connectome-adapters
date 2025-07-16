import logging
from typing import Optional

from src.core.cache.attachment_cache import AttachmentCache
from src.core.cache.message_cache import MessageCache
from src.core.cache.user_cache import UserCache
from src.core.utils.config import Config

class Cache:
    """Cache for storing adapter's data"""

    _instance = None

    @classmethod
    def get_instance(cls, config: Optional[Config] = None, start_maintenance: Optional[bool] = False):
        """Get or create the singleton instance

        Args:
            config: Configuration object (only used during first initialization)
            start_maintenance: Whether to start the maintenance loop
        Returns:
            The singleton Cache instance
        """
        if cls._instance is None:
            cls._instance = cls(config, start_maintenance)
        return cls._instance

    def __init__(self, config: Config, start_maintenance: bool):
        """Initialize the cache

        Args:
            config: Configuration object
            start_maintenance: Whether to start the maintenance loop
        """
        self.config = config
        self.message_cache = MessageCache(config, start_maintenance)
        self.attachment_cache = AttachmentCache(config, start_maintenance)
        self.user_cache = UserCache(config)
