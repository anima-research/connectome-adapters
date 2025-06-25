import asyncio
import logging
import zulip

from typing import List, Dict, Callable, Optional

from src.core.rate_limiter.rate_limiter import RateLimiter
from src.core.utils.config import Config

class Client:
    """Zulip client implementation"""

    def __init__(self, config: Config, process_zulip_event: Callable):
        self.config = config
        self.process_event = process_zulip_event
        self.rate_limiter = RateLimiter.get_instance(self.config)
        self.client = zulip.Client(
            config_file=self.config.get_setting("adapter", "zuliprc_path")
        )
        self.queue_id = None
        self.last_event_id = None
        self.running = False
        self._event_handlers: Dict[str, List[Callable]] = {}
        self._polling_task: Optional[asyncio.Task] = None

    async def connect(self) -> None:
        """Initialize connection and register for events"""
        try:
            result = self.client.register(
                event_types=[
                    "message", "reaction", "update_message",
                    "delete_message", "stream", "subscription", "realm"
                ]
            )

            if result:
                self.queue_id = result["queue_id"]
                self.last_event_id = result["last_event_id"]
                self.running = True

                logging.info(f"Connected to Zulip")
            else:
                logging.error("Failed to connect to Zulip")
        except Exception as e:
            logging.error(f"Error connecting to Zulip: {e}")

    async def start_polling(self) -> None:
        """Start the long polling loop in a separate task"""
        if self._polling_task is None or self._polling_task.done():
            self._polling_task = asyncio.create_task(self._polling_loop())
            logging.info("Started Zulip event polling")

    async def _polling_loop(self) -> None:
        """Long polling loop that runs as a background task"""
        loop = asyncio.get_running_loop()

        while self.running:
            try:
                await self.rate_limiter.limit_request("get_events")
                response = await loop.run_in_executor(
                    None,
                    lambda: self.client.get_events(
                        queue_id=self.queue_id,
                        last_event_id=self.last_event_id,
                        dont_block=False
                    )
                )

                if response and "events" in response:
                    events = response["events"]

                    if events:
                        self.last_event_id = events[-1]["id"]

                    for event in events:
                        await self.process_event(event)
            except Exception as e:
                logging.error(f"Error in polling loop: {e}")

    async def disconnect(self) -> None:
        """Disconnect from Zulip and clean up resources"""
        self.running = False

        if self._polling_task and not self._polling_task.done():
            self._polling_task.cancel()

            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass  # This is expected

        self.queue_id = None
        self.last_event_id = None
        logging.info("Disconnected from Zulip")
