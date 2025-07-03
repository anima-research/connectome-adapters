import asyncio
import json
import logging
import re

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from src.core.conversation.base_manager import BaseManager
from src.core.rate_limiter.rate_limiter import RateLimiter
from src.core.utils.config import Config

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
                 history_limit: Optional[int] = None,
                 message_to_exclude: Optional[Any] = None):
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
            message_to_exclude: Message to exclude from the history
        """
        self.config = config
        self.client = client
        self.conversation_manager = conversation_manager
        self.conversation = self.conversation_manager.get_conversation(conversation_id)
        self.anchor = anchor
        self.before = before
        self.after = after
        self.message_to_exclude = message_to_exclude
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

        logging.info(
            f"Fetching history for conversation {self.conversation.conversation_id} "\
            f"(name [{self.conversation.conversation_name}]) "\
            f"with following params: "\
            f"anchor=[{self.anchor}], "\
            f"before=[{self.before}], "\
            f"after=[{self.after}], "\
            f"history_limit=[{self.history_limit}]"
        )

        if not self.anchor:
            cached_messages = self._fetch_from_cache()
            if len(cached_messages) >= self.history_limit:
                return cached_messages

        return await self._fetch_from_api()

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
        history = self._filter_history(history)
        history.sort(key=lambda x: x["timestamp"])

        if self.before:
            index = len(history) - self.history_limit
            if index > 0:
                return history[index:]

        if self.after and len(history) > self.history_limit:
            return history[:self.history_limit]

        return history

    def _filter_history(self, history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter history according to timestamps

        Args:
            history: List of formatted message history

        Returns:
            List of filtered message history
        """
        if self.message_to_exclude:
            message_id = self.message_to_exclude.get("message_id")
            for msg in history:
                if msg["message_id"] == message_id:
                    history.remove(msg)
        if self.before:
            return [msg for msg in history if msg["timestamp"] < self.before]
        if self.after:
            return [msg for msg in history if msg["timestamp"] > self.after]
        return history

    @abstractmethod
    async def _fetch_from_api(self,
                              num_before: Optional[int] = None,
                              num_after: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch conversation history from the API"""
        raise NotImplementedError("Child classes must implement _fetch_from_api")
