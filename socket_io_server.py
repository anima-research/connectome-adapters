import socketio
import logging
from aiohttp import web
from typing import Optional, Dict, Any

from config import Config

class SocketIOServer:
    """Socket.IO server for communicating with LLM services"""

    def __init__(self):
        """Initialize the Socket.IO server"""
        self.config = Config().get_instance()
        self.sio = socketio.AsyncServer(
            async_mode='aiohttp',
            cors_allowed_origins=self.config.get_setting("socketio.cors_allowed_origins", "*"),
            logger=True
        )
        self.app = web.Application()
        self.sio.attach(self.app)
        self.runner = None
        self.site = None
        self.telegram_bot = None  # Will be set later
        self.connected_clients = set()  # Track connected clients

        @self.sio.event
        async def connect(sid, environ):
            self.connected_clients.add(sid)
            client_count = len(self.connected_clients)
            logging.info(f"LLM client connected: {sid}. Total connected clients: {client_count}")

        @self.sio.event
        async def disconnect(sid):
            if sid in self.connected_clients:
                self.connected_clients.remove(sid)
            client_count = len(self.connected_clients)
            logging.info(f"LLM client disconnected: {sid}. Remaining connected clients: {client_count}")

        @self.sio.event
        async def response_ready(sid, data):
            if self.telegram_bot:
                await self.telegram_bot.handle_llm_response(data)
            else:
                logging.error("Cannot handle LLM response: TelegramBot not set")

    def set_telegram_bot(self, bot):
        """Set the reference to the TelegramBot instance"""
        self.telegram_bot = bot

    async def start(self):
        """Start the Socket.IO server"""
        host = self.config.get_setting("socketio.host", "0.0.0.0")
        port = self.config.get_setting("socketio.port", 8080)

        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, host, port)

        await self.site.start()
        logging.info(f"Socket.IO server started on {host}:{port}")

    async def stop(self):
        """Stop the Socket.IO server"""
        if self.runner:
            await self.runner.cleanup()
            logging.info("Socket.IO server stopped")

    async def broadcast_message(self, message_data: Dict[str, Any]):
        """Broadcast a message to all connected clients"""
        if not self.connected_clients:
            logging.debug("No LLM clients connected, message not broadcasted")
            return

        await self.sio.emit('telegram_message', message_data)
        logging.debug(f"Message broadcasted to {len(self.connected_clients)} LLM clients")
