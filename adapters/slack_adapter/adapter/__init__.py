"""Slack adapter implementation."""

from adapters.slack_adapter.adapter.adapter import Adapter
from adapters.slack_adapter.adapter.slack_client import SlackClient

__all__ = [
    "Adapter",
    "SlackClient"
]
