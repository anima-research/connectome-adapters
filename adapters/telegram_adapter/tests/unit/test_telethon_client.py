import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

from adapters.telegram_adapter.adapter.telethon_client import TelethonClient

class TestTelethonClient:
    """Tests for TelethonClient"""

    @pytest.fixture
    def telethon_client(self, patch_config):
        """Create a TelethonClient with mocked dependencies"""
        yield TelethonClient(patch_config, AsyncMock())

    @pytest.fixture
    def telegram_client_mock(self):
        """Create a mocked TelegramClient instance"""
        client = AsyncMock()
        client.connect = AsyncMock(return_value=None)
        client.is_user_authorized = AsyncMock(return_value=True)
        client.sign_in = AsyncMock()
        client.get_me = AsyncMock()
        client.disconnect = AsyncMock()
        client.on = MagicMock()  # Returns a decorator
        return client

    class TestInitialization:
        """Tests for TelethonClient initialization"""

        def test_initialization(self, telethon_client):
            """Test client initialization with valid config"""
            assert telethon_client.api_id == "12345"
            assert telethon_client.api_hash == "test_hash"
            assert telethon_client.bot_token == "test_bot_token"
            assert telethon_client.phone == "+1234567890"
            assert telethon_client.connected is False
            assert telethon_client.client is None

    class TestConnection:
        """Tests for connecting to Telegram"""

        @pytest.mark.asyncio
        async def test_connect_with_bot_token(self, telethon_client, telegram_client_mock):
            """Test connecting with a bot token"""
            with patch(
                "adapters.telegram_adapter.adapter.telethon_client.TelegramClient",
                return_value=telegram_client_mock
            ):
                me = MagicMock()
                me.username = "test_bot"
                me.first_name = "Test Bot"
                telegram_client_mock.get_me.return_value = me

                result = await telethon_client.connect()

                telegram_client_mock.connect.assert_called_once()
                telegram_client_mock.is_user_authorized.assert_called_once()
                telegram_client_mock.get_me.assert_called_once()

                assert result is True
                assert telethon_client.connected is True
                assert telethon_client.me == me

        @pytest.mark.asyncio
        async def test_connect_with_phone(self, telethon_client, telegram_client_mock):
            """Test connecting with a phone number"""
            telethon_client.bot_token = None

            with patch(
                "adapters.telegram_adapter.adapter.telethon_client.TelegramClient",
                return_value=telegram_client_mock
            ):
                telegram_client_mock.is_user_authorized.return_value = False

                me = MagicMock()
                me.username = None
                me.first_name = "Test User"
                telegram_client_mock.get_me.return_value = me

                with patch("builtins.input", return_value="12345"):
                    result = await telethon_client.connect()

                telegram_client_mock.connect.assert_called_once()
                telegram_client_mock.is_user_authorized.assert_called_once()
                telegram_client_mock.send_code_request.assert_called_once_with("+1234567890")
                telegram_client_mock.sign_in.assert_called_once_with("+1234567890", "12345")
                telegram_client_mock.get_me.assert_called_once()

                assert result is True
                assert telethon_client.connected is True
                assert telethon_client.me == me

        @pytest.mark.asyncio
        @pytest.mark.filterwarnings("ignore::RuntimeWarning")
        async def test_connect_no_credentials(self, telethon_client, telegram_client_mock):
            """Test connecting with no authentication credentials"""
            telethon_client.bot_token = None
            telethon_client.phone = None

            with patch(
                "adapters.telegram_adapter.adapter.telethon_client.TelegramClient",
                return_value=telegram_client_mock
            ):
                telegram_client_mock.is_user_authorized.return_value = False

                with pytest.raises(ValueError):
                    await telethon_client.connect()

                telegram_client_mock.connect.assert_called_once()
                telegram_client_mock.is_user_authorized.assert_called_once()
                telegram_client_mock.sign_in.assert_not_called()
                telegram_client_mock.get_me.assert_not_called()

    class TestDisconnection:
        """Tests for disconnecting from Telegram"""

        @pytest.mark.asyncio
        async def test_disconnect(self, telethon_client, telegram_client_mock):
            """Test disconnecting from Telegram"""
            telethon_client.client = telegram_client_mock
            telethon_client.connected = True

            await telethon_client.disconnect()

            telegram_client_mock.disconnect.assert_called_once()
            assert telethon_client.connected is False
