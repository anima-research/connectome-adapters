import asyncio
import logging
import time

from typing import Any, Callable
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.socket_mode.aiohttp import SocketModeClient
from slack_sdk.socket_mode.response import SocketModeResponse

from core.rate_limiter.rate_limiter import RateLimiter
from core.utils.config import Config

class SlackClient:
    """Slack client implementation using Socket Mode with a single token"""

    def __init__(self, config: Config, process_event: Callable):
        """Initialize the Slack client

        Args:
            config (Config): The configuration for the Slack client
            process_event (Callable): The function to process events
        """
        self.config = config
        self.process_event = process_event
        self.rate_limiter = RateLimiter.get_instance(self.config)

        self.web_client = None
        self.socket_client = None

        self.running = False
        self._connection_task = None
        self._connection_start_time = None

    async def connect(self) -> bool:
        """Connect to Slack using Socket Mode

        Returns:
            bool: True if connection was successful, False otherwise
        """
        try:
            bot_token = self.config.get_setting("adapter", "bot_token")
            app_token = self.config.get_setting("adapter", "app_token")

            if not bot_token or not app_token:
                logging.error("Missing Slack tokens in configuration")
                return False

            self.web_client = AsyncWebClient(token=bot_token)

            try:
                await self.web_client.auth_test()
            except Exception as e:
                logging.error(f"Failed to authenticate with Slack API: {e}")
                return False

            self.socket_client = SocketModeClient(
                app_token=app_token,
                web_client=self.web_client
            )
            self.socket_client.socket_mode_request_listeners.append(
                self._handle_slack_event
            )
            connect_task = asyncio.create_task(self.socket_client.connect())

            try:
                await asyncio.wait_for(asyncio.shield(connect_task), timeout=15)
                self.running = True
                self._connection_task = connect_task
                self._connection_start_time = time.time()
                return True
            except asyncio.TimeoutError:
                logging.error("Timeout while connecting to Slack")
                connect_task.cancel()
                return False
        except Exception as e:
            logging.error(f"Error initiating Slack connection: {e}")
            return False

    async def _handle_slack_event(self, _: Any, request: Any) -> None:
        """Handle incoming Slack events

        Args:
            _: The SocketModeClient that received the event
            req: The event request object
        """
        try:
            response = SocketModeResponse(envelope_id=request.envelope_id)
            await self.socket_client.send_socket_mode_response(response)

            payload = request.payload
            event = payload.get("event", {})
            event.update({"team": payload.get("team_id", "")})

            if float(event.get("event_ts", 0)) < (self._connection_start_time):
                return

            event_type = event.get("type", None)
            event_subtype = event.get("subtype", None)

            if not event_type:
                return

            await self.process_event({
                "type": event_subtype or event_type,
                "event": event
            })
        except Exception as e:
            logging.error(f"Error handling Slack event: {e}")

    async def disconnect(self) -> None:
        """Disconnect from Slack"""
        self.running = False

        try:
            if self._connection_task and not self._connection_task.done():
                self._connection_task.cancel()
                try:
                    await asyncio.wait_for(asyncio.shield(self._connection_task), timeout=5)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    pass  # Expected

            if self.socket_client and await self.socket_client.is_connected():
                try:
                    await asyncio.wait_for(self.socket_client.disconnect(), timeout=5)
                except asyncio.TimeoutError:
                    logging.warning("Timeout while disconnecting from Slack socket")

            self.socket_client = None
            self.web_client = None
            logging.info("Disconnected from Slack")
        except Exception as e:
            logging.error(f"Error disconnecting from Slack: {str(e)}")
