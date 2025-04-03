import asyncio
import discord
import logging

from typing import Any, Optional

from adapters.discord_webhook_adapter.adapter.conversation.manager import Manager
from adapters.discord_webhook_adapter.adapter.event_processors.outgoing_event_processor import OutgoingEventProcessor
from adapters.discord_webhook_adapter.adapter.discord_webhook_client import DiscordWebhookClient

from core.adapter.base_adapter import BaseAdapter
from core.utils.config import Config

class Adapter(BaseAdapter):
    """Discord adapter implementation using Discord"""
    ADAPTER_VERSION = "0.1.0"  # Our adapter version
    TESTED_WITH_API = "v1"     # Discord API version we have tested with

    def __init__(self, config: Config, socketio_server):
        """Initialize the Discord adapter

        Args:
            config: Config instance
            socketio_server: socket_io.server for event broadcasting
        """
        super().__init__(config, socketio_server)
        self.conversation_manager = Manager(config)

    async def _setup_client(self) -> None:
        """Connect to client"""
        self.client = DiscordWebhookClient(self.config)
        self.connected = await self.client.connect()

    async def _get_adapter_info(self) -> None:
        """Get adapter information"""
        pass

    def _print_api_compatibility(self) -> None:
        """Print the API version"""
        logging.info(f"Connected to Discord via webhook")
        logging.info(f"Adapter version {self.ADAPTER_VERSION}, using {self.TESTED_WITH_API}")
        logging.info(f"Discord.py library version: {discord.__version__}")

    def _setup_processors(self) -> None:
        """Setup processors"""
        self.outgoing_events_processor = OutgoingEventProcessor(
            self.config,
            self.client,
            self.conversation_manager
        )

    async def _perform_post_setup_tasks(self) -> None:
        """Perform post setup tasks"""
        pass

    async def _connection_exists(self) -> Optional[Any]:
        """Check webhook connection exists

        Attempts to verify connection to Discord API by making a test request

        Returns:
            Object: Simple object if connection exists, None otherwise
        """
        async with self.client.session.get("https://discord.com/api/v10/gateway") as response:
            if response.status == 200:
                return await response.json()
        return None

    async def _teardown_client(self) -> None:
        """Teardown client"""
        if self.client:
            await self.client.disconnect()
