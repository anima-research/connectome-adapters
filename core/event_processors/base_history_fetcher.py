import asyncio
import json
import logging
import re

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from core.conversation.base_manager import BaseManager
from core.rate_limiter.rate_limiter import RateLimiter
from core.utils.config import Config

class BaseHistoryFetcher(ABC):
    """Fetches and formats history"""

    def __init__(self,
                 config: Config,
                 client: Any,
                 conversation_manager: BaseManager,
                 conversation_id: str,
                 anchor: Optional[str] = None,
                 before: Optional[int] = None,
                 after: Optional[int] = None,
                 history_limit: Optional[int] = None):
        """Initialize the BaseHistoryFetcher

        Args:
            config: Config instance
            client: Client instance
            conversation_manager: Manager instance
            conversation_id: Conversation ID
            anchor: Anchor message ID
            before: Before datetime
            after: After datetime
            history_limit: Limit the number of messages to fetch
        """
        self.config = config
        self.client = client
        self.conversation_manager = conversation_manager
        self.conversation = self.conversation_manager.get_conversation(conversation_id)
        self.anchor = anchor
        self.before = before
        self.after = after
        self.history_limit = history_limit or self.config.get_setting("adapter", "max_history_limit")
        self.cache_fetched_history = self.config.get_setting("caching", "cache_fetched_history")
        self.rate_limiter = RateLimiter.get_instance(self.config)

    async def fetch(self) -> List[Dict[str, Any]]:
        """Fetch conversation history, first checking cache then going to API if needed

        Returns:
            List of formatted message history
        """
        if not self.conversation:
            return []

        api_messages = []
        cached_messages = []

        if self.anchor:
            api_messages = await self._fetch_from_api(self.history_limit, 0)
        else:
            cached_messages = self._fetch_from_cache()

            if len(cached_messages) < self.history_limit:
                if cached_messages:
                    self._update_limits(cached_messages)

                api_messages = await self._fetch_from_api(
                    self.history_limit if self.before else 0,
                    self.history_limit if self.after else 0
                )

        api_messages += cached_messages
        api_messages.sort(key=lambda x: x["timestamp"])

        return api_messages

    def _fetch_from_cache(self) -> List[Dict[str, Any]]:
        """Fetch messages from the cache based on before/after criteria

        Returns:
            List of cached messages matching the criteria
        """
        return self._filter_and_limit_messages(
            self.conversation_manager.get_conversation_cache(
                self.conversation.conversation_id
            )
        )

    def _filter_and_limit_messages(self, history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Apply the history limit to the formatted history

        Args:
            history: List of formatted message history

        Returns:
            List of formatted message history
        """
        if self.before:
            history = [msg for msg in history if msg["timestamp"] <= self.before]
            index = len(history) - self.history_limit
            if index > 0:
                history = history[index:]
        elif self.after:
            history = [msg for msg in history if msg["timestamp"] > self.after]
            if len(history) > self.history_limit:
                history = history[:self.history_limit]

        return history

    @abstractmethod
    async def _fetch_from_api(self,
                              num_before: Optional[int] = None,
                              num_after: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch conversation history from the API"""
        raise NotImplementedError("Child classes must implement _fetch_from_api")

    @abstractmethod
    def _update_limits(self, cached_messages: List[Dict[str, Any]]) -> None:
        """Update the limits based on the cached messages"""
        raise NotImplementedError("Child classes must implement _update_limits")
