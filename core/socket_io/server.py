import asyncio
import logging
import socketio
import time

from aiohttp import web
from dataclasses import dataclass
from typing import Dict, Any, Optional

from core.event_processors.request_events import RequestEvent
from core.utils.config import Config

@dataclass
class SocketIOQueuedEvent:
    """Represents an event queued for processing"""
    data: Dict[str, Any]  # Event data
    sid: str  # Socket ID of sender
    timestamp: float  # When it was queued
    request_id: Optional[str] = None  # Optional ID for tracking/cancellation

class SocketIOServer:
    """Socket.IO server for communicating with LLM services"""

    def __init__(self, config: Config):
        """Initialize the Socket.IO server

        Args:
            config: Config instance
        """
        self.config = config
        self.adapter_type = self.config.get_setting("adapter", "type")
        self.sio = socketio.AsyncServer(
            async_mode="aiohttp",
            cors_allowed_origins=self.config.get_setting(
                "socketio", "cors_allowed_origins", "*"
            ),
            logger=True
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
        self.request_map = {}

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

    async def emit_event(self, event: str, data: Dict[str, Any] = {}) -> None:
        """Emit a status event to all connected clients

        Args:
            event: Event type
            data: Event data
        """
        await self.sio.emit(event, data)
        logging.info(f"Emitted event: {event} with data: {data}")

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

    async def _queue_event(self, sid: str, data: Dict[str, Any]) -> str:
        """Queue an event for processing with rate limiting

        Args:
            sid: Socket ID of the client
            data: Event data

        Returns:
            request_id: ID of the queued request
        """
        request_id = data.get("request_id", f"req_{sid}_{int(time.time() * 1e3)}")
        event = SocketIOQueuedEvent(data, sid, time.time(), request_id)
        self.request_map[request_id] = event
        await self.event_queue.put(event)
        await self.sio.emit(
            "request_queued",
            RequestEvent(adapter_type=self.adapter_type, request_id=request_id).model_dump(),
            room=sid
        )
        logging.debug(f"Queued event with request_id {request_id}")

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
            await self.sio.emit(
                "request_failed",
                RequestEvent(adapter_type=self.adapter_type, request_id=request_id).model_dump(),
                room=sid
            )
            return

        del self.request_map[request_id]
        await self.sio.emit(
            "request_success",
            RequestEvent(adapter_type=self.adapter_type, request_id=request_id).model_dump(),
            room=sid
        )

    async def _process_event_queue(self) -> None:
        """Process events from the queue with rate limiting"""
        logging.info("Starting event queue processor")

        while self.is_processing:
            try:
                event = await self.event_queue.get()

                if event.request_id and event.request_id not in self.request_map:
                    self.event_queue.task_done()
                    continue

                result = await self.adapter.process_outgoing_event(event.data)
                status = "request_success" if result["request_completed"] else "request_failed"
                data = {}

                if result["request_completed"] and "message_ids" in result:
                    data["message_ids"] = result["message_ids"]
                elif result["request_completed"] and "history" in result:
                    data["history"] = result["history"]

                await self.sio.emit(
                    status,
                    RequestEvent(
                        adapter_type=self.adapter_type,
                        request_id=event.request_id,
                        data=data
                    ).model_dump(),
                    room=event.sid
                )

                if event.request_id in self.request_map:
                    del self.request_map[event.request_id]
                self.event_queue.task_done()
            except asyncio.CancelledError:
                logging.info("Event queue processor cancelled")
                break
            except Exception as e:
                logging.error(f"Unexpected error in event queue processor: {e}", exc_info=True)
                await asyncio.sleep(5)  # Prevent tight loop on error
