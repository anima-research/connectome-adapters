import aiohttp
import asyncio
import discord
import pytest
from discord.ext import commands
from unittest.mock import AsyncMock, MagicMock, patch, call

from src.adapters.discord_webhook_adapter.client import Client

class TestClient:
    """Tests for Client"""

    @pytest.fixture
    def bot_mock(self):
        """Create a mocked Discord Bot"""
        bot_mock = AsyncMock(spec=commands.Bot)
        bot_mock.start = AsyncMock()
        bot_mock.close = AsyncMock()

        # Mock guilds
        guild_mock = MagicMock(spec=discord.Guild)
        guild_mock.id = 987654321

        # Mock channels
        channel_mock = MagicMock(spec=discord.TextChannel)
        channel_mock.id = 123456789
        channel_mock.permissions_for = MagicMock(return_value=MagicMock(manage_webhooks=True))
        channel_mock.create_webhook = AsyncMock()

        # Set up guild.get_channel
        guild_mock.get_channel = MagicMock(return_value=channel_mock)

        # Mock user
        user_mock = MagicMock(spec=discord.ClientUser)
        user_mock.id = 12345678
        user_mock.name = "Test Bot"

        # Set up the relationships
        bot_mock.guilds = [guild_mock]
        bot_mock.user = user_mock

        # Set up guild.webhooks
        existing_webhook = MagicMock(spec=discord.Webhook)
        existing_webhook.user = user_mock
        existing_webhook.channel_id = 123456789
        existing_webhook.url = "https://discord.com/api/webhooks/123456789/token"
        existing_webhook.name = "Existing Webhook"
        guild_mock.webhooks = AsyncMock(return_value=[existing_webhook])

        # Set up bot.get_guild
        bot_mock.get_guild = MagicMock(return_value=guild_mock)

        return bot_mock

    @pytest.fixture
    def session_mock(self):
        """Create a mocked aiohttp ClientSession"""
        session_mock = AsyncMock(spec=aiohttp.ClientSession)
        response_mock = AsyncMock()
        response_mock.status = 200
        response_mock.json = AsyncMock(return_value={"url": "wss://gateway.discord.gg"})
        session_mock.get = AsyncMock(return_value=response_mock)
        session_mock.closed = False
        return session_mock

    @pytest.fixture
    def rate_limiter_mock(self):
        """Create a mock rate limiter"""
        rate_limiter = AsyncMock()
        rate_limiter.limit_request = AsyncMock(return_value=None)
        rate_limiter.get_wait_time = AsyncMock(return_value=0)
        return rate_limiter

    @pytest.fixture
    def discord_webhook_client(self, discord_webhook_config, rate_limiter_mock):
        """Create a DiscordWebhookClient with mocked config"""
        discord_webhook_config.get_setting = MagicMock(side_effect=lambda section, key, default=None: {
            ("adapter", "bot_connections"): [
                {
                    "application_id": "12345678",
                    "bot_token": "test_token1"
                },
                {
                    "application_id": "87654321",
                    "bot_token": "test_token2"
                }
            ],
            ("adapter", "webhooks"): [
                {
                    "conversation_id": "111111/222222",
                    "url": "https://discord.com/api/webhooks/222222/token",
                    "name": "Config Webhook"
                }
            ]
        }.get((section, key), default))

        client = Client(discord_webhook_config)
        client.rate_limiter = rate_limiter_mock
        return client

    class TestConnection:
        """Tests for connecting to Discord"""

        @pytest.mark.asyncio
        async def test_connect_success(self, discord_webhook_client, bot_mock, session_mock):
            """Test successful connection to Discord"""
            with patch("aiohttp.ClientSession", return_value=session_mock):
                discord_webhook_client._connect_bot = AsyncMock(return_value=True)
                discord_webhook_client.bots = {
                    "test_token1": bot_mock,
                    "test_token2": bot_mock
                }
                discord_webhook_client._load_webhooks = AsyncMock()

                with patch("asyncio.gather", AsyncMock(return_value=[True, True])):
                    with patch("asyncio.create_task", side_effect=lambda coro: coro):
                        assert await discord_webhook_client.connect() is True

                        assert discord_webhook_client._connect_bot.call_count == 2
                        discord_webhook_client._connect_bot.assert_has_calls([
                            call("test_token1"),
                            call("test_token2")
                        ], any_order=True)

                        assert discord_webhook_client.running is True
                        assert discord_webhook_client.session is session_mock
                        discord_webhook_client._load_webhooks.assert_awaited_once()

    class TestDisconnection:
        """Tests for disconnecting from Discord"""

        @pytest.mark.asyncio
        @pytest.mark.filterwarnings("ignore::RuntimeWarning")
        async def test_disconnect_with_active_tasks(self, discord_webhook_client):
            """Test disconnecting with active connection tasks"""
            discord_webhook_client.running = True
            discord_webhook_client.session = AsyncMock()
            discord_webhook_client.session.close = AsyncMock()

            bot1 = AsyncMock()
            bot1.close = AsyncMock()
            bot2 = AsyncMock()
            bot2.close = AsyncMock()
            discord_webhook_client.bots = {
                "test_token1": bot1,
                "test_token2": bot2
            }

            task1 = MagicMock()
            task1.done.return_value = False
            task1.cancel = MagicMock()

            task2 = MagicMock()
            task2.done.return_value = True
            task2.cancel = MagicMock()

            discord_webhook_client._connection_tasks = [task1, task2]

            await discord_webhook_client.disconnect()

            assert discord_webhook_client.running is False
            bot1.close.assert_awaited_once()
            bot2.close.assert_awaited_once()
            task1.cancel.assert_called_once()
            task2.cancel.assert_not_called()

    class TestWebhookManagement:
        """Tests for webhook management"""

        @pytest.mark.asyncio
        @pytest.mark.filterwarnings("ignore::RuntimeWarning")
        async def test_load_webhooks(self, discord_webhook_client, bot_mock):
            """Test loading webhooks from Discord and config"""
            discord_webhook_client.bots = {
                "test_token1": bot_mock,
                "test_token2": bot_mock
            }

            await discord_webhook_client._load_webhooks()

            assert len(discord_webhook_client.webhooks) == 2
            assert "987654321/123456789" in discord_webhook_client.webhooks
            assert discord_webhook_client.webhooks["987654321/123456789"]["url"] == "https://discord.com/api/webhooks/123456789/token"
            assert discord_webhook_client.webhooks["987654321/123456789"]["name"] == "Existing Webhook"

            assert "111111/222222" in discord_webhook_client.webhooks
            assert discord_webhook_client.webhooks["111111/222222"]["url"] == "https://discord.com/api/webhooks/222222/token"
            assert discord_webhook_client.webhooks["111111/222222"]["name"] == "Config Webhook"

            assert discord_webhook_client.rate_limiter.limit_request.call_count == 2

        @pytest.mark.asyncio
        async def test_get_existing_webhook(self, discord_webhook_client):
            """Test getting an existing webhook"""
            discord_webhook_client.webhooks = {
                "987654321/123456789": {
                    "url": "https://discord.com/api/webhooks/123456789/token",
                    "name": "Test Webhook"
                }
            }

            result = await discord_webhook_client.get_or_create_webhook("987654321/123456789")
            assert result == {
                "url": "https://discord.com/api/webhooks/123456789/token",
                "name": "Test Webhook"
            }

        @pytest.mark.asyncio
        @pytest.mark.filterwarnings("ignore::RuntimeWarning")
        async def test_create_new_webhook(self, discord_webhook_client, bot_mock):
            """Test creating a new webhook"""
            discord_webhook_client.bots = {
                "test_token1": bot_mock,
                "test_token2": bot_mock
            }

            guild = bot_mock.get_guild.return_value
            channel = guild.get_channel.return_value

            new_webhook = MagicMock(spec=discord.Webhook)
            new_webhook.url = "https://discord.com/api/webhooks/new/token"
            new_webhook.name = "New Webhook"
            channel.create_webhook.return_value = new_webhook

            result = await discord_webhook_client.get_or_create_webhook("987654321/123456789")
            assert result == {
                "url": "https://discord.com/api/webhooks/new/token",
                "name": "New Webhook",
                "bot_token": "test_token1"
            }

            assert "987654321/123456789" in discord_webhook_client.webhooks
            assert discord_webhook_client.webhooks["987654321/123456789"] == result
            channel.create_webhook.assert_awaited_once_with(name="Connectome Bot")
