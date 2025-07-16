import pytest
import asyncio

from unittest.mock import AsyncMock, MagicMock, patch
from src.adapters.zulip_adapter.client import Client

class TestZulipClient:
    """Tests for ZulipClient"""

    @pytest.fixture
    def zulip_mock(self):
        """Create a mocked Zulip Client instance directly"""
        with patch("zulip.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.register = MagicMock(return_value={
                "queue_id": "test_queue_id",
                "last_event_id": 12345
            })
            mock_client.get_events = MagicMock(return_value={
                "events": [
                    {"id": 12346, "type": "message", "content": "test message"},
                    {"id": 12347, "type": "reaction", "emoji_name": "heart"}
                ]
            })
            mock_client_class.return_value = mock_client
            yield mock_client

    @pytest.fixture
    def zulip_client(self, zulip_config, zulip_mock, rate_limiter_mock):
        """Create a ZulipClient with mocked dependencies"""
        client = Client(zulip_config, AsyncMock())
        client.client = zulip_mock
        client.rate_limiter = rate_limiter_mock
        yield client

    class TestInitialization:
        """Tests for ZulipClient initialization"""

        def test_initialization(self, zulip_config):
            """Test client initialization with valid config"""
            with patch("zulip.Client") as mock_client_class:
                mock_client = MagicMock()
                mock_client_class.return_value = mock_client

                process_event_mock = AsyncMock()
                client = Client(zulip_config, process_event_mock)

                assert client.config == zulip_config
                assert client.queue_id is None
                assert client.last_event_id is None
                assert client.running is False
                assert client._polling_task is None

                mock_client_class.assert_called_once_with(
                    config_file=zulip_config.get_setting("adapter", "zuliprc_path")
                )

    class TestConnection:
        """Tests for connecting to Zulip"""

        @pytest.mark.asyncio
        async def test_connect_success(self, zulip_client, zulip_mock):
            """Test successful connection to Zulip"""
            with patch.object(zulip_client, "client", zulip_mock):
                await zulip_client.connect()

                zulip_mock.register.assert_called_once_with(
                    event_types=[
                        "message", "reaction",
                        "update_message", "delete_message",
                        "stream", "subscription", "realm"
                    ]
                )

                assert zulip_client.queue_id == "test_queue_id"
                assert zulip_client.last_event_id == 12345
                assert zulip_client.running is True

        @pytest.mark.asyncio
        async def test_connect_failure_empty_result(self, zulip_client, zulip_mock):
            """Test connecting with empty result"""
            zulip_mock.register.return_value = None

            with patch.object(zulip_client, "client", zulip_mock):
                await zulip_client.connect()

                zulip_mock.register.assert_called_once()
                assert zulip_client.running is False

        @pytest.mark.asyncio
        async def test_connect_exception(self, zulip_client, zulip_mock):
            """Test connecting with an exception"""
            zulip_mock.register.side_effect = Exception("Test error")

            with patch.object(zulip_client, "client", zulip_mock):
                await zulip_client.connect()

                zulip_mock.register.assert_called_once()
                assert zulip_client.running is False

    class TestDisconnection:
        """Tests for disconnecting from Zulip"""

        @pytest.mark.asyncio
        @pytest.mark.filterwarnings("ignore::RuntimeWarning")
        async def test_disconnect(self, zulip_client, zulip_mock):
            """Test disconnecting with an active polling task"""
            zulip_client.running = True
            zulip_client.queue_id = "test_queue_id"
            zulip_client._polling_task = AsyncMock()

            with patch.object(zulip_client, "client", zulip_mock):
                await zulip_client.disconnect()

                assert zulip_client.running is False
                assert zulip_client.queue_id is None
                assert zulip_client.last_event_id is None
