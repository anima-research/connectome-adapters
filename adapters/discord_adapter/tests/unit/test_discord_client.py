import pytest
import asyncio
import discord
from discord.ext import commands
from unittest.mock import AsyncMock, MagicMock, patch, call

from adapters.discord_adapter.adapter.discord_client import DiscordClient

class TestDiscordClient:
    """Tests for DiscordClient"""

    @pytest.fixture
    def bot_mock(self):
        """Create a mocked Discord Bot"""
        bot_mock = AsyncMock(spec=commands.Bot)
        bot_mock.event = MagicMock()
        bot_mock.event.side_effect = lambda func: func  # Simulate decorator
        return bot_mock

    @pytest.fixture
    def rate_limiter_mock(self):
        """Create a mock rate limiter"""
        rate_limiter = AsyncMock()
        rate_limiter.limit_request = AsyncMock(return_value=None)
        rate_limiter.get_wait_time = AsyncMock(return_value=0)
        return rate_limiter

    @pytest.fixture
    def discord_client(self, patch_config, bot_mock, rate_limiter_mock):
        """Create a DiscordClient with mocked dependencies"""
        client = DiscordClient(patch_config, AsyncMock())
        client.bot = bot_mock
        client.rate_limiter = rate_limiter_mock
        return client

    class TestConnection:
        """Tests for connecting to Discord"""

        @pytest.mark.asyncio
        @pytest.mark.filterwarnings("ignore::RuntimeWarning")
        async def test_connect(self, discord_client):
            """Test successful connection to Discord"""
            task_mock = MagicMock()
            task_mock.done.return_value = False

            with patch('asyncio.create_task', return_value=task_mock) as create_task_mock:
                with patch('asyncio.sleep') as sleep_mock:
                    assert await discord_client.connect() is True
                    create_task_mock.assert_called_once()
                    sleep_mock.assert_called_once_with(1)

        @pytest.mark.asyncio
        @pytest.mark.filterwarnings("ignore::RuntimeWarning")
        async def test_connect_exception(self, discord_client):
            """Test connection with an exception during task creation"""
            with patch('asyncio.create_task', side_effect=Exception("Task creation error")):
                assert await discord_client.connect() is False

    class TestDisconnection:
        """Tests for disconnecting from Discord"""

        @pytest.mark.asyncio
        @pytest.mark.filterwarnings("ignore::RuntimeWarning")
        async def test_disconnect(self, discord_client):
            """Test disconnecting with a completed connection task"""
            task_mock = MagicMock()
            task_mock.done.return_value = True
            discord_client._connection_task = task_mock
            discord_client.running = True

            await discord_client.disconnect()

            assert discord_client.running is False
            discord_client.bot.close.assert_awaited_once()
            task_mock.cancel.assert_not_called()
