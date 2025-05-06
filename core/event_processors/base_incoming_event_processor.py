import asyncio
import json
import logging

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List

from core.event_processors.incoming_event_builder import IncomingEventBuilder
from core.rate_limiter.rate_limiter import RateLimiter
from core.utils.config import Config

class BaseIncomingEventProcessor(ABC):
    """Incoming events processor"""

    def __init__(self, config: Config, client: Any):
        """Initialize the incoming events processor

        Args:
            config: Config instance
            client: Client instance
        """
        self.config = config
        self.client = client
        self.rate_limiter = RateLimiter.get_instance(self.config)
        self.incoming_event_builder = IncomingEventBuilder(
            self.config.get_setting("adapter", "adapter_type"),
            self.config.get_setting("adapter", "adapter_name")
        )

    async def process_event(self, event: Any) -> List[Dict[str, Any]]:
        """Process events from a client

        Args:
            event: Event object

        Returns:
            List of standardized event dictionaries to emit
        """
        try:
            event_handlers = self._get_event_handlers()
            handler = event_handlers.get(event["type"])

            if handler:
                return await handler(event)

            logging.debug(f"Unhandled event type: {event['type']}")
            return []
        except Exception as e:
            logging.error(f"Error processing event: {e}", exc_info=True)
            return []

    @abstractmethod
    def _get_event_handlers(self) -> Dict[str, Callable]:
        """Get event handlers for incoming events"""
        raise NotImplementedError("Child classes must implement _get_event_handlers")
