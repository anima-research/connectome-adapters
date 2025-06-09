"""Slack loaders implementation."""

from src.adapters.slack_adapter.attachment_loaders.downloader import Downloader
from src.adapters.slack_adapter.attachment_loaders.uploader import Uploader

__all__ = [
    "Downloader",
    "Uploader"
]
