import aiohttp
import asyncio
import json
import logging
import discord
from discord.ext import commands

from typing import Any, Dict, Optional
from src.core.rate_limiter.rate_limiter import RateLimiter
from src.core.utils.config import Config

class Client:
    """Discord webhook client implementation"""

    def __init__(self, config: Config):
        """Initialize the Discord webhook client

        Args:
            config (Config): The configuration for the Discord webhook client
        """
        self.config = config

        self.bot_configs = self.config.get_setting(
            "adapter", "bot_connections", default=[]
        )
        self.bots = {}

        for bot_config in self.bot_configs:
            intents = discord.Intents.default()
            intents.guilds = True
            self.bots[bot_config["bot_token"]] = commands.Bot(
                command_prefix='!',
                intents=intents,
                application_id=int(bot_config["application_id"])
            )

        self._connection_tasks = []
        self.session = None
        self.running = False
        self.webhooks = {}
        self.rate_limiter = RateLimiter.get_instance(self.config)

    async def connect(self) -> bool:
        """Initialize HTTP session

        Returns:
            bool: True if connection successful
        """
        try:
            if self.session is None or self.session.closed:
                self.session = aiohttp.ClientSession()

            connection_tasks = []
            for bot_token in self.bots:
                task = asyncio.create_task(self._connect_bot(bot_token))
                connection_tasks.append(task)
                self._connection_tasks.append(task)
            await asyncio.gather(*connection_tasks, return_exceptions=True)

            self.running = True
            await self._load_webhooks()

            logging.info(f"Discord webhook client initialized with {len(self.webhooks)} webhooks")
            return True
        except Exception as e:
            logging.error(f"Error initializing webhook client: {e}")
            return False

    async def disconnect(self) -> None:
        """Close HTTP session"""
        self.running = False

        try:
            if self.session and not self.session.closed:
                await self.session.close()

            for bot_token in self.bots:
                try:
                    await self.bots[bot_token].close()
                except Exception as e:
                    logging.error(f"Error closing bot connection: {e}")

            for task in self._connection_tasks:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass  # Expected

            logging.info("Webhook client session closed")
        except Exception as e:
            logging.error(f"Error closing webhook client session: {e}")

    async def get_or_create_webhook(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Create a webhook in the specified channel if possible

        Args:
            conversation_id: Conversation ID to create webhook in
        """
        if conversation_id in self.webhooks:
            return self.webhooks[conversation_id]

        try:
            guild_id, channel_id = conversation_id.split("/")
            if not guild_id or not channel_id:
                logging.error(f"There is no guild or channel for conversation {conversation_id}")
                return None

            for bot_token in self.bots:
                guild = self.bots[bot_token].get_guild(int(guild_id))
                if not guild:
                    continue

                channel = guild.get_channel(int(channel_id))
                if not channel:
                    continue

                if not channel.permissions_for(guild.me).manage_webhooks:
                    logging.error(f"No permission to create webhooks in conversation {conversation_id}")
                    return None

                webhook = await channel.create_webhook(name="Connectome Bot")
                self.webhooks[conversation_id] = {
                    "url": webhook.url,
                    "name": webhook.name,
                    "bot_token": bot_token
                }

                logging.info(f"Created webhook in conversation {conversation_id}")
                return self.webhooks[conversation_id]
        except Exception as e:
            logging.error(f"Error creating webhook: {e}")

        return None

    def get_client_bot(self, bot_token: str) -> Optional[Any]:
        """Get the bot for a conversation

        Args:
            bot_token: Bot token

        Returns:
            Bot object or None if not found
        """
        return self.bots.get(bot_token, None)

    async def _connect_bot(self, bot_token) -> bool:
        """Connect a single bot

        Args:
            bot_token: Bot token

        Returns:
            bool: True if connection successful
        """
        try:
            asyncio.create_task(self.bots[bot_token].start(bot_token))
            await asyncio.sleep(1)
            return True
        except Exception as e:
            logging.error(f"Error connecting bot: {e}")
            return False

    async def _load_webhooks(self) -> None:
        """Load webhook configuration from config and from Discord"""
        try:
            # Load webhooks from Discord
            for bot_token in self.bots:
                if not self.bots[bot_token].is_ready():
                    await asyncio.sleep(3)

                for guild in self.bots[bot_token].guilds:
                    await self.rate_limiter.limit_request("load_webhooks")
                    for webhook in await guild.webhooks():
                        self.webhooks[f"{guild.id}/{webhook.channel_id}"] = {
                            "url": webhook.url,
                            "name": webhook.name,
                            "bot_token": bot_token
                        }

            # Load additional webhooks from file
            for webhook in self.config.get_setting("adapter", "webhooks", default=[]):
                if webhook["conversation_id"] and webhook["conversation_id"] not in self.webhooks:
                    self.webhooks[webhook["conversation_id"]] = {
                        "url": webhook["url"],
                        "name": webhook["name"],
                        "bot_token": None
                    }
        except Exception as e:
            logging.error(f"Error loading webhooks: {e}")
