import pytest
import discord
import pytest

from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from src.adapters.discord_adapter.event_processors.discord_utils import (
    get_discord_channel,
    is_discord_service_message
)

class TestDiscordUtils:
    """Tests Discord utils"""

    def test_is_service_message(self):
        """Test service message detection"""
        # Create regular message
        regular_message = MagicMock()
        regular_message.type = discord.MessageType.default
        assert is_discord_service_message(regular_message) is False

        # Create reply message
        reply_message = MagicMock()
        reply_message.type = discord.MessageType.reply
        assert is_discord_service_message(reply_message) is False

        # Create service message (pins_add)
        pins_add_message = MagicMock()
        pins_add_message.type = discord.MessageType.pins_add
        assert is_discord_service_message(pins_add_message) is True

        # Create service message (new_member)
        new_member_message = MagicMock()
        new_member_message.type = discord.MessageType.new_member
        assert is_discord_service_message(new_member_message) is True

    @pytest.mark.asyncio
    async def test_get_discord_channel_from_cache(self):
        """Test getting a channel that's in the cache"""
        client_mock = MagicMock()

        async def async_fetch_channel(*args, **kwargs):
            return MagicMock()

        channel_mock = MagicMock()
        client_mock.get_channel = MagicMock(return_value=channel_mock)
        client_mock.fetch_channel = AsyncMock(side_effect=async_fetch_channel)

        # Test with a guild/channel format
        conversation_id = "987654321/123456789"
        result = await get_discord_channel(client_mock, conversation_id)

        assert result is channel_mock
        client_mock.get_channel.assert_called_once_with(123456789)
        client_mock.fetch_channel.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_discord_channel_fetch_needed(self):
        """Test getting a channel that needs to be fetched"""
        client_mock = MagicMock()
        client_mock.get_channel = MagicMock(return_value=None)
        channel_mock = MagicMock()

        async def async_fetch_channel(*args, **kwargs):
            return channel_mock
        client_mock.fetch_channel = AsyncMock(side_effect=async_fetch_channel)

        # Test with just a channel ID
        conversation_id = "123456789"
        result = await get_discord_channel(client_mock, conversation_id)

        assert result is channel_mock
        client_mock.get_channel.assert_called_once_with(123456789)
        client_mock.fetch_channel.assert_called_once_with(123456789)

    @pytest.mark.asyncio
    async def test_get_discord_channel_not_found(self):
        """Test getting a channel that doesn't exist"""
        client_mock = MagicMock()
        client_mock.get_channel = MagicMock(return_value=None)

        async def async_fetch_channel(*args, **kwargs):
            return None
        client_mock.fetch_channel = AsyncMock(side_effect=async_fetch_channel)

        conversation_id = "123456789"

        with pytest.raises(Exception, match=r"Channel 123456789 not found"):
            await get_discord_channel(client_mock, conversation_id)
