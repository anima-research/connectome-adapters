import asyncio
import logging

from slack_sdk import version as slack_sdk_version
from typing import Any, Optional

from adapters.slack_adapter.adapter.conversation.manager import Manager
from adapters.slack_adapter.adapter.event_processors.incoming_event_processor import IncomingEventProcessor
from adapters.slack_adapter.adapter.event_processors.incoming_file_processor import IncomingFileProcessor
from adapters.slack_adapter.adapter.event_processors.outgoing_event_processor import OutgoingEventProcessor
from adapters.slack_adapter.adapter.slack_client import SlackClient

from core.adapter.base_adapter import BaseAdapter
from core.utils.config import Config

class Adapter(BaseAdapter):
    """Slack adapter implementation using Slack"""
    ADAPTER_VERSION = "0.1.0"  # Our adapter version
    TESTED_WITH_API = "v1"     # Slack API version we have tested with

    def __init__(self, config: Config, socketio_server, start_maintenance=False):
        """Initialize the Slack adapter

        Args:
            config: Config instance
            socketio_server: socket_io.server for event broadcasting
            start_maintenance: Whether to start the maintenance loop
        """
        super().__init__(config, socketio_server, start_maintenance)
        self.conversation_manager = Manager(config, start_maintenance)
        self.file_processor = None

    async def process_incoming_event(self, event: Any) -> None:
        """Process events from client

        Args:
            event_type: event type
            event: client's event object
        """
        if event.get("type") == "file_share":
            await self.file_processor.schedule_file_processing(event["event"])
        else:
            await super().process_incoming_event(event)

    async def _setup_client(self) -> None:
        """Connect to client"""
        self.client = SlackClient(self.config, self.process_incoming_event)
        self.connected = await self.client.connect()

    async def _get_adapter_info(self) -> None:
        """Get adapter information about the connected Slack bot"""
        auth_test_result = await self.client.web_client.auth_test()
        self.config.add_setting(
            "adapter", "adapter_id", auth_test_result.get("user_id", "")
        )
        self.config.add_setting(
            "adapter", "adapter_name", auth_test_result.get("user", "")
        )

    def _print_api_compatibility(self) -> None:
        """Print the API version"""
        logging.info(f"Connected to Slack")
        logging.info(f"Adapter version {self.ADAPTER_VERSION}, using {self.TESTED_WITH_API}")
        logging.info(f"Slack SDK version: {slack_sdk_version.__version__}")

    def _setup_processors(self) -> None:
        """Setup processors"""
        self.incoming_events_processor = IncomingEventProcessor(
            self.config,
            self.client.web_client,
            self.conversation_manager
        )
        self.file_processor = IncomingFileProcessor(
            self.config,
            self.client.web_client,
            self
        )
        self.outgoing_events_processor = OutgoingEventProcessor(
            self.config,
            self.client.web_client,
            self.conversation_manager
        )

    async def _perform_post_setup_tasks(self) -> None:
        """Perform post setup tasks"""
        pass

    async def _connection_exists(self) -> Optional[Any]:
        """Check connection

        Returns:
            Object: User object if connection exists, None otherwise
        """
        return await self.client.web_client.auth_test()

    async def _reconnect_with_client(self) -> None:
        """Reconnect with client"""
        if self.client:
            logging.info("Attempting to reconnect Slack client")
            await self.client.reconnect()
            self.connected = self.client.running

    async def _teardown_client(self) -> None:
        """Teardown client"""
        if self.client:
            await self.client.disconnect()
            self.client = None
