"""Discord loaders implementation."""

from src.adapters.discord_adapter.event_processing.attachment_loaders.downloader import Downloader
from src.adapters.discord_adapter.event_processing.attachment_loaders.uploader import Uploader

__all__ = [
    "Downloader",
    "Uploader"
]
