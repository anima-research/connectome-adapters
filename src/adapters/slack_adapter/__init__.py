"""Slack adapter implementation."""

from src.adapters.slack_adapter.adapter import Adapter
from src.adapters.slack_adapter.client import Client

__all__ = [
    "Adapter",
    "Client"
]
