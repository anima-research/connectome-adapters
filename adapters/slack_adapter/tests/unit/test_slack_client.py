import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch, call

from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.socket_mode.aiohttp import SocketModeClient
from slack_sdk.socket_mode.response import SocketModeResponse

from adapters.slack_adapter.adapter.slack_client import SlackClient

class TestSlackClient:
    """Tests for SlackClient"""

    @pytest.fixture
    def socket_client_mock(self):
        """Create a mocked SocketModeClient"""
        client = AsyncMock(spec=SocketModeClient)
        client.connect = AsyncMock()
        client.disconnect = AsyncMock()
        client.is_connected = MagicMock(return_value=True)
        client.send_socket_mode_response = AsyncMock()
        client.socket_mode_request_listeners = []
        return client

    @pytest.fixture
    def rate_limiter_mock(self):
        """Create a mock rate limiter"""
        rate_limiter = AsyncMock()
        rate_limiter.limit_request = AsyncMock(return_value=None)
        rate_limiter.get_wait_time = AsyncMock(return_value=0)
        return rate_limiter

    @pytest.fixture
    def slack_client(self, patch_config, rate_limiter_mock):
        """Create a SlackClient with mocked dependencies"""
        client = SlackClient(patch_config, AsyncMock())
        client.rate_limiter = rate_limiter_mock
        return client

    class TestEventHandling:
        """Tests for event handling"""

        @pytest.mark.asyncio
        async def test_handle_slack_event(self, slack_client, socket_client_mock):
            """Test handling a valid Slack event"""
            process_event_mock = AsyncMock()
            slack_client.process_event = process_event_mock
            slack_client._connection_start_time = time.time() - 10
            slack_client.socket_client = socket_client_mock
            request = MagicMock()
            request.envelope_id = "env_123"
            request.payload = {
                "event": {
                    "type": "message",
                    "text": "Hello",
                    "event_ts": str(time.time())
                },
                "team_id": "T12345"
            }

            await slack_client._handle_slack_event(None, request)

            socket_client_mock.send_socket_mode_response.assert_awaited_once()
            process_event_mock.assert_awaited_once()

            called_event = process_event_mock.call_args[0][0]
            assert called_event["type"] == "message"
            assert called_event["event"]["text"] == "Hello"
            assert called_event["event"]["team"] == "T12345"

        @pytest.mark.asyncio
        async def test_handle_old_event(self, slack_client, socket_client_mock):
            """Test handling an event that occurred before connection"""
            process_event_mock = AsyncMock()
            slack_client.process_event = process_event_mock
            slack_client._connection_start_time = time.time()
            slack_client.socket_client = socket_client_mock
            request = MagicMock()
            request.envelope_id = "env_123"
            request.payload = {
                "event": {
                    "type": "message",
                    "text": "Old message",
                    "event_ts": str(time.time() - 60)  # 60 seconds in the past
                },
                "team_id": "T12345"
            }

            await slack_client._handle_slack_event(None, request)

            # Verify response was sent but event was not processed
            socket_client_mock.send_socket_mode_response.assert_awaited_once()
            process_event_mock.assert_not_awaited()

        @pytest.mark.asyncio
        async def test_handle_event_with_subtype(self, slack_client, socket_client_mock):
            """Test handling an event with a subtype"""
            process_event_mock = AsyncMock()
            slack_client.process_event = process_event_mock
            slack_client._connection_start_time = time.time() - 10
            slack_client.socket_client = socket_client_mock
            request = MagicMock()
            request.envelope_id = "env_123"
            request.payload = {
                "event": {
                    "type": "message",
                    "subtype": "message_changed",
                    "text": "Edited message",
                    "event_ts": str(time.time())
                },
                "team_id": "T12345"
            }

            await slack_client._handle_slack_event(None, request)

            # Verify the subtype was used as the event type
            called_event = process_event_mock.call_args[0][0]
            assert called_event["type"] == "message_changed"
