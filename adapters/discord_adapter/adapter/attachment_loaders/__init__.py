"""Discord loaders implementation."""

from adapters.discord_adapter.adapter.attachment_loaders.downloader import Downloader
from adapters.discord_adapter.adapter.attachment_loaders.uploader import Uploader

__all__ = [
    "Downloader",
    "Uploader"
]
