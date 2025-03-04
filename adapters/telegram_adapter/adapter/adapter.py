import asyncio
import json
import logging
import os
import telethon

from typing import Any, Optional

from adapters.telegram_adapter.adapter.conversation.manager import Manager
from adapters.telegram_adapter.adapter.event_processors.incoming_event_processor import IncomingEventProcessor
from adapters.telegram_adapter.adapter.event_processors.outgoing_event_processor import OutgoingEventProcessor
from adapters.telegram_adapter.adapter.telethon_client import TelethonClient

from core.adapter.base_adapter import BaseAdapter
from core.utils.config import Config

class Adapter(BaseAdapter):
    """Telegram adapter implementation using Telethon"""
    ADAPTER_VERSION = "0.1.0"  # Our adapter version
    TESTED_WITH_API = "8.3"    # Telegram API version we've tested with

    def __init__(self, config: Config, socketio_server, start_maintenance=False):
        """Initialize the Telegram adapter

        Args:
            config: Config instance
            socketio_server: socket_io.server for event broadcasting
            start_maintenance: Whether to start the maintenance loop
        """
        super().__init__(config, socketio_server, start_maintenance)
        self.conversation_manager = Manager(config, start_maintenance)

    async def _setup_client(self) -> None:
        """Connect to client"""
        self.client = TelethonClient(self.config, self.process_incoming_event)
        self.connected = await self.client.connect()

    async def _get_adapter_info(self) -> None:
        """Get adapter information"""
        await self.rate_limiter.limit_request("get_me")
        adapter_info = await self.client.client.get_me()
        self.config.add_setting(
            "adapter", "adapter_id", str(getattr(adapter_info, "id", ""))
        )
        self.config.add_setting(
            "adapter", "adapter_name", getattr(adapter_info, "username", None)
        )

    def _print_api_compatibility(self) -> None:
        """Print the API version"""
        logging.info(f"Connected to Telegram")
        logging.info(f"Adapter version {self.ADAPTER_VERSION}, using {self.TESTED_WITH_API}")
        logging.info(f"Telethon library version: {telethon.__version__}")

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
        pass

    async def _connection_exists(self) -> Optional[Any]:
        """Check connection

        Returns:
            Telethon ME object: object if connected, None otherwise
        """
        await self.rate_limiter.limit_request("get_me")
        return await self.client.client.get_me()

    async def _teardown_client(self) -> None:
        """Teardown client"""
        try:
            await self.client.disconnect()
            logging.info("Disconnected from Telegram")
        except Exception as e:
            logging.error(f"Error disconnecting from Telegram: {e}")
