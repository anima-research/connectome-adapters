"""Slack conversation manager implementation."""

from src.adapters.slack_adapter.conversation.data_classes import ConversationInfo
from src.adapters.slack_adapter.conversation.manager import Manager, SlackEventType
from src.adapters.slack_adapter.conversation.message_builder import MessageBuilder
from src.adapters.slack_adapter.conversation.thread_handler import ThreadHandler
from src.adapters.slack_adapter.conversation.reaction_handler import ReactionHandler

__all__ = [
    "ConversationInfo",
    "Manager",
    "MessageBuilder",
    "ReactionHandler",
    "ThreadHandler",
    "SlackEventType"
]
