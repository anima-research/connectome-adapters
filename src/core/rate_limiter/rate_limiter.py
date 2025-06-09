import asyncio
import time
import logging
from typing import Dict, Optional
from src.core.utils.config import Config

class RateLimiter:
    """Rate limiter for API requests"""

    _instance = None

    @classmethod
    def get_instance(cls, config: Config):
        """Get or create the singleton instance

        Args:
            config: Configuration object (only used during first initialization)

        Returns:
            The singleton RateLimiter instance
        """
        if cls._instance is None:
            cls._instance = cls(config)
        return cls._instance

    def __init__(self, config: Config):
        """Initialize the rate limiter

        Args:
            config: Configuration object
        """
        self.config = config

        # Requests per minute globally
        self.global_rpm = self.config.get_setting("rate_limit", "global_rpm")
        # Requests per minute per conversation
        self.per_conversation_rpm = self.config.get_setting("rate_limit", "per_conversation_rpm")
        # Messages per minute
        self.message_rpm = self.config.get_setting("rate_limit", "message_rpm")

        # Tracking state
        self.last_global_request = 0
        self.last_conversation_requests: Dict[str, float] = {}
        self.last_message_request = 0

        # Tracking counts for monitoring
        self.global_request_count = 0
        self.per_conversation_request_counts: Dict[str, int] = {}

    async def get_wait_time(self,
                            request_type: str,
                            conversation_id: Optional[str] = None) -> float:
        """Get the wait time before making a request

        Args:
            request_type: Type of request (message, media, general)
            conversation_id: Conversation ID for per-conversation limits

        Returns:
            Wait time in seconds
        """
        try:
          current_time = time.time()
          wait_times = []

          global_time_since = current_time - self.last_global_request
          global_wait = max(0, (60 / self.global_rpm) - global_time_since)
          wait_times.append(global_wait)

          if conversation_id:
              conversation_time_since = current_time - self.last_conversation_requests.get(conversation_id, 0)
              conversation_wait = max(0, (60 / self.per_conversation_rpm) - conversation_time_since)
              wait_times.append(conversation_wait)

          if request_type == "message":
              msg_time_since = current_time - self.last_message_request
              msg_wait = max(0, (60 / self.message_rpm) - msg_time_since)
              wait_times.append(msg_wait)

          return max(wait_times)
        except Exception as e:
            logging.error(f"Error calculating wait time: {e}")
            return 1.0

    async def limit_request(self,
                            request_type: str,
                            conversation_id: Optional[str] = None) -> None:
        """Apply rate limiting before making a request

        Args:
            request_type: Type of request (message, media, general)
            conversation_id: Conversation ID for per-conversation limits
        """
        wait_time = await self.get_wait_time(request_type, conversation_id)

        if wait_time > 0:
            logging.debug(f"Rate limiting: waiting {wait_time:.2f} seconds")
            await asyncio.sleep(wait_time)

        current_time = time.time()
        self.last_global_request = current_time

        if conversation_id:
            self.last_conversation_requests[conversation_id] = current_time
            self.per_conversation_request_counts[conversation_id] = self.per_conversation_request_counts.get(conversation_id, 0) + 1

        if request_type == "message":
            self.last_message_request = current_time

        self.global_request_count += 1
