import asyncio
import logging

from typing import Any, Dict
from src.adapters.text_file_adapter.event_processor.file_event_cache import FileEventCache
from src.adapters.text_file_adapter.event_processor.processor import Processor
from src.core.utils.config import Config

class Adapter():
    """Text file adapter implementation"""

    def __init__(self, config: Config, socketio_server):
        """Initialize adapter

        Args:
            config: Config instance
            socketio_server: socket_io.server for event broadcasting
        """
        self.socketio_server = socketio_server
        self.config = config
        self.adapter_type = self.config.get_setting("adapter", "adapter_type")
        self.running = False
        self.monitoring_task = None
        self.outgoing_events_processor = None

    async def start(self) -> None:
        """Start the adapter"""
        logging.info("Starting adapter...")

        self.running = True
        self.monitoring_task = asyncio.create_task(self._monitor_connection())
        self.file_event_cache = FileEventCache(self.config, True)
        await self.file_event_cache.start()
        self.outgoing_events_processor = Processor(self.config, self.file_event_cache)
        await self._emit_event("connect")

        logging.info("Adapter started successfully")

    async def _monitor_connection(self) -> None:
        """Monitor connection to client"""
        check_interval = self.config.get_setting(
            "adapter", "connection_check_interval"
        )

        while self.running:
            await asyncio.sleep(check_interval)
            await self._emit_event("connect")

    async def _emit_event(self, event_type: str) -> None:
        """Emit event

        Args:
            event_type: event type (connect, disconnect)
        """
        await self.socketio_server.emit_event(
            event_type, {"adapter_type": self.adapter_type}
        )

    async def stop(self) -> None:
        """Stop the adapter"""
        if not self.running:
            return
        self.running = False

        if self.monitoring_task:
            self.monitoring_task.cancel()

        if self.file_event_cache:
            await self.file_event_cache.stop()

        await self._emit_event("disconnect")
        logging.info("Adapter stopped")

    async def process_outgoing_event(self, data: Any) -> Dict[str, Any]:
        """Process events from socket_io.client

        Args:
            data: data for event

        Returns:
            Dict[str, Any]: Dictionary containing the status and data fields if applicable
        """
        return await self.outgoing_events_processor.process_event(data)
