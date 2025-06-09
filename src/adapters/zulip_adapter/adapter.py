import asyncio
import logging
import zulip

from typing import Any, Optional

from src.adapters.zulip_adapter.conversation.manager import Manager
from src.adapters.zulip_adapter.event_processors.incoming_event_processor import IncomingEventProcessor
from src.adapters.zulip_adapter.event_processors.outgoing_event_processor import OutgoingEventProcessor
from src.adapters.zulip_adapter.client import Client

from src.core.adapter.base_adapter import BaseAdapter
from src.core.utils.config import Config

class Adapter(BaseAdapter):
    """Zulip adapter implementation using Zulip"""
    ADAPTER_VERSION = "0.1.0"  # Our adapter version
    TESTED_WITH_API = "v1"     # Zulip API version we have tested with

    def __init__(self, config: Config, socketio_server, start_maintenance=False):
        """Initialize the Zulip adapter

        Args:
            config: Config instance
            socketio_server: socket_io.server for event broadcasting
            start_maintenance: Whether to start the maintenance loop
        """
        super().__init__(config, socketio_server, start_maintenance)
        self.conversation_manager = Manager(config, start_maintenance)

    async def _setup_client(self) -> None:
        """Connect to client"""
        self.client = Client(self.config, self.process_incoming_event)
        await self.client.connect()
        self.connected = self.client.running

    async def _get_adapter_info(self) -> None:
        """Get adapter information"""
        await self.rate_limiter.limit_request("get_profile")
        adapter_info = self.client.client.get_profile()
        self.config.add_setting("adapter", "adapter_email", adapter_info.get("email", ""))
        self.config.add_setting("adapter", "adapter_name", adapter_info.get("full_name", ""))
        self.config.add_setting("adapter", "adapter_id", str(adapter_info.get("user_id", "")))

    def _print_api_compatibility(self) -> None:
        """Print the API version"""
        logging.info(f"Connected to Zulip")
        logging.info(f"Adapter version {self.ADAPTER_VERSION}, using {self.TESTED_WITH_API}")
        logging.info(f"Zulip library version: {zulip.__version__}")

    def _setup_processors(self) -> None:
        """Setup processors"""
        self.incoming_events_processor = IncomingEventProcessor(
            self.config,
            self.client.client,
            self.conversation_manager
        )
        self.outgoing_events_processor = OutgoingEventProcessor(
            self.config,
            self.client.client,
            self.conversation_manager
        )

    async def _perform_post_setup_tasks(self) -> None:
        """Perform post setup tasks"""
        await self.client.start_polling()

    async def _connection_exists(self) -> Optional[Any]:
        """Check connection

        Returns:
            Any: True if connection exists, False otherwise
        """
        await self.rate_limiter.limit_request("get_profile")
        response = self.client.client.get_profile()
        return response and response.get("result", None) == "success"

    async def _reconnect_with_client(self) -> None:
        """Reconnect with client"""
        if self.client:
            logging.info("Attempting to reconnect Zulip client")
            await self.client.disconnect()
            await self.client.connect()
            self.connected = self.client.running

            if self.connected:
                logging.info("Zulip client reconnected successfully")
                await self.client.start_polling()
            else:
                logging.error("Failed to reconnect Zulip client")

    async def _teardown_client(self) -> None:
        """Teardown client"""
        if self.client:
            await self.client.disconnect()
