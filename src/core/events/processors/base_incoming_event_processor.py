import asyncio
import json
import logging

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional

from src.core.events.builders.incoming_event_builder import IncomingEventBuilder
from src.core.rate_limiter.rate_limiter import RateLimiter
from src.core.utils.config import Config

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
            self.config.get_setting("adapter", "adapter_name"),
            self.config.get_setting("adapter", "adapter_id")
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

    async def _handle_fetch_history(self, event: Any) -> List[Dict[str, Any]]:
        """Fetch conversation history

        Args:
            event: fetch_history event object

        Returns:
            List of events to emit
        """
        return [
            self.incoming_event_builder.history_fetched(
                event["event"],
                await self._fetch_history(
                    event["event"].get("conversation_id", None),
                    before=event["event"].get("before", None),
                    after=event["event"].get("after", None),
                    limit=event["event"].get("limit", None)
                )
            )
        ]

    async def _fetch_history(self,
                             conversation_id: str,
                             anchor: Optional[str] = None,
                             before: Optional[int] = None,
                             after: Optional[int] = None,
                             limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch conversation history

        Args:
            conversation_id: str containing conversation_id
            before: int containing before timestamp
            after: int containing after timestamp
            limit: int containing limit

        Returns:
            List of formatted message history
        """
        try:
            fetcher_class = self._history_fetcher_class()
            return await fetcher_class(
                self.config,
                self.client,
                self.conversation_manager,
                conversation_id,
                anchor=anchor,
                before=before,
                after=after,
                history_limit=limit
            ).fetch()
        except Exception as e:
            logging.error(f"Error fetching conversation history: {e}", exc_info=True)
            return []

    @abstractmethod
    def _history_fetcher_class(self):
        """History fetcher class"""
        raise NotImplementedError("Child classes must implement _history_fetcher_class")
