"""Slack loaders implementation."""

from adapters.slack_adapter.adapter.attachment_loaders.downloader import Downloader
from adapters.slack_adapter.adapter.attachment_loaders.uploader import Uploader

__all__ = [
    "Downloader",
    "Uploader"
]
