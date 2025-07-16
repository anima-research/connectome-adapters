import asyncio
import logging

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.core.utils.config import Config

@dataclass
class UserInfo():
    """Information about a user"""
    user_id: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None
    email: Optional[str] = None
    is_bot: bool = False

    @property
    def display_name(self) -> str:
        """Get a human-readable display name"""
        if self.username:
            return f"{self.username}"

        name_parts = []
        if self.first_name:
            name_parts.append(self.first_name)
        if self.last_name:
            name_parts.append(self.last_name)
        if name_parts:
            return " ".join(name_parts)

        if self.email:
            return self.email

        return f"User {self.user_id}"

class UserCache:
    """Tracks and manages user info"""

    def __init__(self, config: Config, start_maintenance=False):
        """Initialize the MessageCache

        Args:
            config: Config instance
            start_maintenance: Whether to start the maintenance loop
        """
        self.config = config
        self.users: Dict[str, UserInfo] = {}  # user_id -> user_info

    def get_user_by_id(self, user_id: str) -> Optional[UserInfo]:
        """Get a specific user by ID

        Args:
            conversation_id: Conversation ID
            message_id: Message ID

        Returns:
            UserInfo object or None if not found
        """
        return self.users.get(user_id, None)

    def add_user(self, user_info: Dict[str, Any]) -> None:
        """Add a user to the cache

        Args:
            user_info: User info dictionary

        Returns:
            UserInfo object
        """
        cached_user = self.get_user_by_id(user_info["user_id"])

        if cached_user:
            return cached_user

        self.users[user_info["user_id"]] = UserInfo(
            user_id=user_info["user_id"],
            first_name=user_info.get("first_name", None),
            last_name=user_info.get("last_name", None),
            username=user_info.get("username", None),
            email=user_info.get("email", None),
            is_bot=user_info.get("is_bot", False)
        )

        return self.users[user_info["user_id"]]

    def delete_user(self, user_id: str) -> None:
        """Delete a user from the cache

        Args:
            user_id: ID of the user to delete
        """
        if user_id in self.users:
            del self.users[user_id]
