"""Telegram loaders implementation."""

from adapters.telegram_adapter.adapter.attachment_loaders.base_loader import BaseLoader
from adapters.telegram_adapter.adapter.attachment_loaders.uploader import Uploader
from adapters.telegram_adapter.adapter.attachment_loaders.downloader import Downloader

__all__ = [
    "BaseLoader",
    "Uploader",
    "Downloader"
]
