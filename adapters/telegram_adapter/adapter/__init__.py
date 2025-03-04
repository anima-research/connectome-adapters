"""Telegram adapter implementation."""

from adapters.telegram_adapter.adapter.adapter import Adapter
from adapters.telegram_adapter.adapter.telethon_client import TelethonClient

__all__ = [
    "Adapter",
    "TelethonClient"
]
