import asyncio
import logging
import discord
from discord.ext import commands

from typing import Callable, Optional

from src.core.rate_limiter.rate_limiter import RateLimiter
from src.core.utils.config import Config

class Client:
    """Discord client implementation"""

    def __init__(self, config: Config, process_event: Callable):
        """Initialize the Discord client

        Args:
            config (Config): The configuration for the Discord client
            process_event (Callable): The function to process events
        """
        self.config = config
        self.process_event = process_event
        self.rate_limiter = RateLimiter.get_instance(self.config)

        intents = discord.Intents.default()
        intents.message_content = True  # Needed to read message content
        intents.reactions = True        # Needed for reaction events
        intents.guilds = True

        self.bot = commands.Bot(
            command_prefix='!',
            intents=intents,
            application_id=int(self.config.get_setting("adapter", "application_id"))
        )
        self._setup_event_handlers()

        self.running = False
        self._connection_task: Optional[asyncio.Task] = None

    def _setup_event_handlers(self) -> None:
        """Set up Discord event handlers"""
        @self.bot.event
        async def on_ready():
            self.running = True

        @self.bot.event
        async def on_message(message):
            await self.process_event({"type": "new_message", "event": message})

        @self.bot.event
        async def on_raw_message_edit(payload):
            await self.process_event({"type": "edited_message", "event": payload})

        @self.bot.event
        async def on_raw_message_delete(payload):
            await self.process_event({"type": "deleted_message", "event": payload})

        @self.bot.event
        async def on_raw_reaction_add(payload):
            await self.process_event({"type": "added_reaction", "event": payload})

        @self.bot.event
        async def on_raw_reaction_remove(payload):
            await self.process_event({"type": "removed_reaction", "event": payload})

        @self.bot.event
        async def on_guild_channel_update(_, after):
            await self.process_event({"type": "renamed_conversation", "event": after})

        @self.bot.event
        async def on_thread_update(_, after):
            await self.process_event({"type": "renamed_conversation", "event": after})

        @self.bot.event
        async def on_guild_update(before, after):
            await self.process_event({"type": "renamed_server", "event": after})

    async def connect(self) -> bool:
        """Connect to Discord"""
        try:
            self._connection_task = asyncio.create_task(
                self.bot.start(self.config.get_setting("adapter", "bot_token"))
            )
            await asyncio.sleep(1)

            if self._connection_task.done():
                raise Exception(self._connection_task.exception())

            logging.info("Discord connection initiated successfully")
            return True
        except Exception as e:
            logging.error(f"Error initiating Discord connection: {e}")
            return False

    async def disconnect(self) -> None:
        """Disconnect from Discord"""
        self.running = False

        try:
            await self.bot.close()

            if self._connection_task and not self._connection_task.done():
                self._connection_task.cancel()
                try:
                    await self._connection_task
                except asyncio.CancelledError:
                    pass  # Expected

            logging.info("Disconnected from Discord")
        except Exception as e:
            logging.error(f"Error disconnecting from Discord: {e}")
