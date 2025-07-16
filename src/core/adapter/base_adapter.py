import asyncio
import logging

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from src.core.events.models.connection_events import ConnectionEvent
from src.core.rate_limiter.rate_limiter import RateLimiter
from src.core.utils.config import Config

class BaseAdapter(ABC):
    """Base adapter implementation.

    This abstract base class defines the common interface and behavior for
    all platform-specific adapters. It follows the template method pattern,
    where the base class defines the skeleton of operations and child classes
    implement specific steps.

    Child classes must implement:
    - _setup_client: Connect to the platform API
    - _get_adapter_info: Retrieve adapter-specific information
    - _print_api_compatibility: Log API compatibility information
    - _setup_processors: Initialize event processors
    - _perform_post_setup_tasks: Execute any additional setup tasks
    - _check_connection: Verify the connection is still active
    - _teardown_client: Clean up platform connections
    """

    def __init__(self, config: Config, socketio_server):
        """Initialize adapter

        Args:
            config: Config instance
            socketio_server: socket_io.server for event broadcasting
        """
        self.socketio_server = socketio_server
        self.config = config
        self.adapter_type = config.get_setting("adapter", "adapter_type")
        self.running = False
        self.connected = False
        self.initialized = False
        self.monitoring_task = None
        self.client = None
        self.outgoing_events_processor = None
        self.incoming_events_processor = None
        self.rate_limiter = RateLimiter.get_instance(self.config)
        self.max_reconnect_attempts = self.config.get_setting("adapter", "max_reconnect_attempts")
        self.current_reconnect_attempt = 0

    async def start(self) -> None:
        """Start the adapter"""
        logging.info("Starting adapter...")
        self.running = True

        try:
            await self._setup_client()

            if self.connected:
                self.initialized = True

                await self._get_adapter_info()
                self._print_api_compatibility()
                self._setup_processors()
                await self._perform_post_setup_tasks()
                self._setup_monitoring()
                await self._emit_event("connect")

                logging.info("Adapter started successfully")
                return
        except Exception as e:
            logging.error(f"Error starting adapter: {e}", exc_info=True)
            await self._emit_event("disconnect")

        self.running = False

    @abstractmethod
    async def _setup_client(self) -> None:
        """Connect to client"""
        raise NotImplementedError("Child classes must implement _setup_client")

    @abstractmethod
    async def _get_adapter_info(self) -> None:
        """Get adapter information"""
        raise NotImplementedError("Child classes must implement _get_adapter_info")

    @abstractmethod
    def _print_api_compatibility(self) -> None:
        """Print the API version"""
        raise NotImplementedError("Child classes must implement _print_api_compatibility")

    @abstractmethod
    def _setup_processors(self) -> None:
        """Setup processors"""
        raise NotImplementedError("Child classes must implement _setup_processors")

    @abstractmethod
    async def _perform_post_setup_tasks(self) -> None:
        """Perform post setup tasks"""
        raise NotImplementedError("Child classes must implement _perform_post_setup_tasks")

    def _setup_monitoring(self) -> None:
        """Setup monitoring"""
        self.monitoring_task = asyncio.create_task(self._monitor_connection())

    async def _monitor_connection(self) -> None:
        """Monitor connection to client"""
        check_interval = self.config.get_setting("adapter", "connection_check_interval")
        retry_delay = self.config.get_setting("adapter", "retry_delay")

        while self.running:
            try:
                await asyncio.sleep(check_interval)

                if not self.initialized or not self.running:
                    continue

                if not await self._connection_exists():
                    if self.current_reconnect_attempt >= self.max_reconnect_attempts:
                        raise RuntimeError("Connection check failed")

                    self.current_reconnect_attempt += 1
                    await self._reconnect_with_client()
                    continue

                self.current_reconnect_attempt = 0
                await self._emit_event("connect")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Error in connection monitor: {e}")

                await self._emit_event("disconnect")
                await asyncio.sleep(retry_delay)

    @abstractmethod
    async def _connection_exists(self) -> Optional[Any]:
        """Check connection"""
        raise NotImplementedError("Child classes must implement _connection_exists")

    @abstractmethod
    async def _reconnect_with_client(self) -> None:
        """Reconnect with client"""
        raise NotImplementedError("Child classes must implement _reconnect_with_client")

    async def _emit_event(self, event_type: str) -> None:
        """Emit event

        Args:
            event_type: event type (connect, disconnect)
        """
        await self.socketio_server.emit_event(
            event_type, ConnectionEvent(adapter_type=self.adapter_type).model_dump()
        )

    async def stop(self) -> None:
        """Stop the adapter"""
        if not self.running:
            return
        self.running = False

        if self.monitoring_task:
            self.monitoring_task.cancel()

        await self._teardown_client()
        self.connected = False

        await self._emit_event("disconnect")
        logging.info("Adapter stopped")

    @abstractmethod
    async def _teardown_client(self) -> None:
        """Teardown client"""
        raise NotImplementedError("Child classes must implement _teardown_client")

    async def process_incoming_event(self, event: Any) -> None:
        """Process events from client

        Args:
            event_type: event type
            event: client's event object
        """
        for event_info in await self.incoming_events_processor.process_event(event):
            await self.socketio_server.emit_event("bot_request", event_info)

    async def process_outgoing_event(self, data: Any) -> Dict[str, Any]:
        """Process events from socket_io.client

        Args:
            data: data for event

        Returns:
            Dict[str, Any]: Dictionary containing the status and data fields if applicable
        """
        if not self.client:
            logging.error("Adapter is not connected to perform action")
            return {
                "request_completed": False,
                "error": "Adapter is not connected to perform action"
            }

        result = await self.outgoing_events_processor.process_event(data)
        if self._incoming_event_should_be_triggered(data, result):
            asyncio.create_task(
                self.process_incoming_event(
                    self._convert_outgoing_event_to_incoming_one(data)
                )
            )

        return result

    def _incoming_event_should_be_triggered(self,
                                            data: Any,
                                            outgoing_event_result: Dict[str, Any]) -> bool:
        """Check if incoming event should be triggered

        Args:
            data: data for event
            outgoing_event_result: result of outgoing event

        Returns:
            bool: True if incoming event should be triggered, False otherwise
        """
        outgoing_events_that_should_trigger_incoming_ones = ["fetch_history"]

        return (
            data["event_type"] in outgoing_events_that_should_trigger_incoming_ones and
            outgoing_event_result["request_completed"]
        )

    def _convert_outgoing_event_to_incoming_one(self, data: Any) -> Any:
        """Convert outgoing event to incoming one

        Args:
            data: data for event

        Returns:
            Any: converted data
        """
        data["type"] = data["event_type"]
        del data["event_type"]
        data["event"] = data["data"].copy()
        del data["data"]
        return data
