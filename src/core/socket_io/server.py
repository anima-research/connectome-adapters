import asyncio
import logging
import socketio
import time
import uuid
from aiohttp import web
from dataclasses import dataclass
from typing import Dict, Any, Optional

from src.core.events.builders.request_event_builder import RequestEventBuilder
from src.core.utils.config import Config

@dataclass
class SocketIOQueuedEvent:
    """Represents an event queued for processing"""
    data: Dict[str, Any]  # Event data
    sid: str  # Socket ID of sender
    timestamp: float  # When it was queued
    request_id: Optional[str] = None  # Optional ID for tracking/cancellation
    internal_request_id: Optional[str] = None  # Optional external ID for tracking

class SocketIOServer:
    """Socket.IO server for communicating with LLM services"""
    ADAPTER_STOPPED_ERROR = "Not processed due to adapter stopping"

    def __init__(self, config: Config):
        """Initialize the Socket.IO server

        Args:
            config: Config instance
        """
        self.config = config
        self.adapter_type = self.config.get_setting("adapter", "adapter_type")
        self.sio = socketio.AsyncServer(
            async_mode="aiohttp",
            cors_allowed_origins=self.config.get_setting(
                "socketio", "cors_allowed_origins", "*"
            ),
            logger=True,
            ping_interval=65,
            ping_timeout=60
        )
        self.app = web.Application()
        self.sio.attach(self.app)
        self.runner = None
        self.site = None
        self.adapter = None  # Will be set later
        self.connected_clients = set()  # Track connected clients

        self.event_queue = asyncio.Queue()
        self.processing_task = None
        self.is_processing = False
        self.is_stopping = False
        self.request_map = {}
        self.request_event_builder = RequestEventBuilder(self.adapter_type)

        @self.sio.event
        async def connect(sid, environ):
            self.connected_clients.add(sid)
            logging.info(f"LLM client connected: {sid}")

        @self.sio.event
        async def disconnect(sid):
            if sid in self.connected_clients:
                self.connected_clients.remove(sid)
            logging.info(f"LLM client disconnected: {sid}.")

        @self.sio.event
        async def cancel_request(sid, data):
            """Handle request to send a message to adapter"""
            await self._cancel_request(sid, data.get("data"))

        @self.sio.event
        async def bot_response(sid, data):
            """Handle request to send a message to adapter"""
            await self._queue_event(sid, data)

    def set_adapter(self, adapter: Any) -> None:
        """Set the reference to the adapter instance

        Args:
            adapter: Adapter instance
        """
        self.adapter = adapter

    async def start(self) -> None:
        """Start the Socket.IO server"""
        host = self.config.get_setting("socketio", "host")
        port = self.config.get_setting("socketio", "port")

        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, host, port)
        await self.site.start()
        logging.info(f"Socket.IO server started on {host}:{port}")

        self.is_processing = True
        self.processing_task = asyncio.create_task(self._process_event_queue())
        logging.info("Event queue processor started")

    async def stop(self) -> None:
        """Stop the Socket.IO server"""
        self.is_stopping = True

        while not self.event_queue.empty():
            await self._process_single_event()

        if self.is_processing:
            self.is_processing = False
            if self.processing_task:
                self.processing_task.cancel()
                try:
                    await self.processing_task
                except asyncio.CancelledError:
                    pass
            logging.info("Event queue processor stopped")

        if self.runner:
            await self.runner.cleanup()
            logging.info("Socket.IO server stopped")

    async def emit_event(self, event: str, data: Dict[str, Any] = {}) -> None:
        """Emit a status event to all connected clients

        Args:
            event: Event type
            data: Event data
        """
        await self.sio.emit(event, data)
        print(f"Emitted event: {event} with data: {data}")

    async def emit_request_queued_event(self, data: Dict[str, Any] = {}) -> None:
        """Emit a request queued event to all connected clients

        Args:
            event: Event type
            data: Event data
        """
        await self.emit_event("request_queued", data)

    async def emit_request_failed_event(self, data: Dict[str, Any] = {}) -> None:
        """Emit a request failed event to all connected clients

        Args:
            event: Event type
            data: Event data
        """
        await self.emit_event("request_failed", data)

    async def emit_request_success_event(self, data: Dict[str, Any] = {}) -> None:
        """Emit a request success event to all connected clients

        Args:
            event: Event type
            data: Event data
        """
        await self.emit_event("request_success", data)

    async def _queue_event(self, sid: str, data: Dict[str, Any]) -> str:
        """Queue an event for processing with rate limiting

        Args:
            sid: Socket ID of the client
            data: Event data

        Returns:
            request_id: ID of the queued request
        """
        request_id = data.get("request_id", f"req_{time.time():.6f}_{uuid.uuid4()}")
        internal_request_id = None

        if "internal_request_id" in data:
            internal_request_id = data["internal_request_id"]
            del data["internal_request_id"]

        event = SocketIOQueuedEvent(data, sid, time.time(), request_id, internal_request_id)

        if self.is_stopping:
            await self.emit_request_failed_event(
                self._build_request_event(
                    request_id, internal_request_id, {"error": self.ADAPTER_STOPPED_ERROR}
                )
            )
            return

        self.request_map[request_id] = event
        self.event_queue.put_nowait(event)

        logging.info(f"Queued event with request_id {request_id}")
        await self.emit_request_queued_event(self._build_request_event(request_id, internal_request_id))

    async def _process_event_queue(self) -> None:
        """Process events from the queue with rate limiting"""
        logging.info("Starting event queue processor")

        while self.is_processing:
            await self._process_single_event()

    async def _process_single_event(self) -> None:
        """Process a request event"""
        try:
            event = self.event_queue.get_nowait()
        except asyncio.QueueEmpty:
            await asyncio.sleep(1)
            return

        if event.request_id and event.request_id not in self.request_map:
            self.event_queue.task_done()
            return

        logging.info(f"Processing event: {event.request_id}")

        try:
            result = {}
            if not self.is_stopping:
                result = await self.adapter.process_outgoing_event(event.data)

            request_event_data = self.request_event_builder.build(
                event.request_id,
                event.internal_request_id,
                self._build_request_event_data(event, result)
            ).model_dump()

            if result.get("request_completed", False):
                await self.emit_request_success_event(request_event_data)
            else:
                await self.emit_request_failed_event(request_event_data)

            if event.request_id in self.request_map:
                del self.request_map[event.request_id]
            self.event_queue.task_done()
        except asyncio.CancelledError:
            logging.info("Event queue processor cancelled")
        except Exception as e:
            logging.error(f"Unexpected error in event queue processor: {e}", exc_info=True)
            await asyncio.sleep(5)  # Prevent tight loop on error

    async def _cancel_request(self, sid: str, data: Dict[str, Any]) -> None:
        """Cancel a queued request if it hasn't been processed yet

        Args:
            sid: Socket ID of the client
            data: Event data
        """
        request_id = data.get("request_id")

        if not request_id:
            return

        if request_id not in self.request_map:
            await self.emit_request_failed_event(
                self._build_request_event(
                    request_id,
                    data.get("internal_request_id", None),
                    {"error": "Request ID not found in request map"}
                )
            )
            return

        del self.request_map[request_id]
        logging.info(f"Request with request_id {request_id} cancelled successfully")

        await self.emit_request_success_event(
            self.request_event_builder.build(
                request_id, data.get("internal_request_id", None)
            ).model_dump()
        )

    def _build_request_event(self,
                             request_id: str,
                             internal_request_id: Optional[str] = None,
                             data: Dict[str, Any] = {}) -> Dict[str, Any]:
        """Build a request event

        Args:
            request_id: Request ID
            internal_request_id: Internal Request ID
            data: Event data

        Returns:
            data: The data for the request event
        """
        return self.request_event_builder.build(
            request_id, internal_request_id, data
        ).model_dump()

    def _build_request_event_data(self,
                                  event: SocketIOQueuedEvent,
                                  result: Dict[str, Any]) -> Dict[str, Any]:
        """Build the data for the request event

        Args:
            event: The event to build the data for
            result: The result of the request

        Returns:
            data: The data for the request event
        """
        if self.is_stopping:
            return {
                "error": self.ADAPTER_STOPPED_ERROR,
                "affected_message_id": event.data.get("data", {}).get("message_id", None)
            }

        data = {}
        affected_message_id = event.data.get("data", {}).get("message_id", None)

        if "message_ids" in result:
            data["message_ids"] = result["message_ids"]
        elif "content" in result:
            data["content"] = result["content"]
        elif "file_content" in result:
            data["file_content"] = result["file_content"]
        elif "directories" in result and "files" in result:
            data["directories"] = result["directories"]
            data["files"] = result["files"]
        elif "error" in result:
            data["error"] = result["error"]
            data["affected_message_id"] = affected_message_id

        return data
