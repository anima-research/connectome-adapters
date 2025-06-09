"""Telegram loaders implementation."""

from src.adapters.telegram_adapter.attachment_loaders.base_loader import BaseLoader
from src.adapters.telegram_adapter.attachment_loaders.uploader import Uploader
from src.adapters.telegram_adapter.attachment_loaders.downloader import Downloader

__all__ = [
    "BaseLoader",
    "Uploader",
    "Downloader"
]
