import asyncio
import os
import pytest
import time

from unittest.mock import AsyncMock, MagicMock, patch

from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.socket_mode.aiohttp import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest

from src.adapters.slack_adapter.adapter import Adapter
from src.adapters.slack_adapter.client import Client
from src.adapters.slack_adapter.attachment_loaders.uploader import Uploader
from src.adapters.slack_adapter.attachment_loaders.downloader import Downloader
from src.adapters.slack_adapter.conversation.data_classes import ConversationInfo
from src.adapters.slack_adapter.event_processors.outgoing_event_processor import OutgoingEventProcessor
from src.adapters.slack_adapter.event_processors.incoming_event_processor import IncomingEventProcessor
from src.adapters.slack_adapter.event_processors.incoming_file_processor import IncomingFileProcessor

class TestSlackToSocketIOFlowIntegration:
    """Integration tests for Slack to socket.io flow"""

    # =============== FIXTURES ===============

    @pytest.fixture
    def socketio_mock(self):
        """Create a mocked Socket.IO server"""
        socketio = MagicMock()
        socketio.emit_event = AsyncMock()
        return socketio

    @pytest.fixture
    def web_client_mock(self):
        """Create a mocked Slack Web API client"""
        client = AsyncMock(spec=AsyncWebClient)
        client.auth_test = AsyncMock(return_value={
            "ok": True,
            "bot_id": "B12345",
            "user": "test-bot",
            "team": "T12345"
        })
        client.chat_postMessage = AsyncMock(return_value={
            "ok": True,
            "ts": "1662031200.123456"
        })
        client.chat_update = AsyncMock(return_value={"ok": True})
        client.chat_delete = AsyncMock(return_value={"ok": True})
        client.reactions_add = AsyncMock(return_value={"ok": True})
        client.reactions_remove = AsyncMock(return_value={"ok": True})
        client.users_info = AsyncMock(return_value={
            "ok": True,
            "user": {
                "id": "U12345678",
                "name": "slackuser",
                "real_name": "Slack User",
                "profile": {
                    "display_name": "Slack User"
                }
            }
        })
        return client

    @pytest.fixture
    def socket_client_mock(self):
        """Create a mocked Slack Socket Mode client"""
        client = AsyncMock(spec=SocketModeClient)
        client.connect = AsyncMock()
        client.disconnect = AsyncMock()
        client.is_connected = MagicMock(return_value=True)
        client.send_socket_mode_response = AsyncMock()
        client.socket_mode_request_listeners = []
        return client

    @pytest.fixture
    def slack_client_mock(self, web_client_mock, socket_client_mock):
        """Create a mocked Slack client"""
        client = MagicMock(spec=Client)
        client.web_client = web_client_mock
        client.socket_client = socket_client_mock
        client.running = True
        client.connect = AsyncMock(return_value=True)
        client.disconnect = AsyncMock()
        return client

    @pytest.fixture
    def downloader_mock(self):
        """Create a mocked Downloader"""
        downloader_mock = AsyncMock(spec=Downloader)
        downloader_mock.download_attachments = AsyncMock(return_value=[])
        return downloader_mock

    @pytest.fixture
    def uploader_mock(self):
        """Create a mocked Uploader"""
        uploader_mock = AsyncMock(spec=Uploader)
        uploader_mock.upload_attachments = AsyncMock(return_value=[])
        return uploader_mock

    @pytest.fixture
    def rate_limiter_mock(self):
        """Create a mock rate limiter"""
        rate_limiter = AsyncMock()
        rate_limiter.limit_request = AsyncMock(return_value=None)
        rate_limiter.get_wait_time = AsyncMock(return_value=0)
        return rate_limiter

    @pytest.fixture
    def adapter(self,
                slack_config,
                socketio_mock,
                slack_client_mock,
                downloader_mock,
                uploader_mock,
                rate_limiter_mock):
        """Create a Slack adapter with mocked dependencies"""
        adapter = Adapter(slack_config, socketio_mock)
        adapter.client = slack_client_mock
        adapter.rate_limiter = rate_limiter_mock
        adapter.connected = True
        adapter.initialized = True

        adapter.outgoing_events_processor = OutgoingEventProcessor(
            slack_config, slack_client_mock.web_client, adapter.conversation_manager
        )
        adapter.outgoing_events_processor.uploader = uploader_mock
        adapter.outgoing_events_processor.rate_limiter = rate_limiter_mock

        adapter.incoming_events_processor = IncomingEventProcessor(
            slack_config, slack_client_mock.web_client, adapter.conversation_manager
        )
        adapter.incoming_events_processor.rate_limiter = rate_limiter_mock
        adapter.incoming_events_processor.downloader = downloader_mock

        adapter.file_processor = IncomingFileProcessor(
            slack_config, slack_client_mock.web_client, adapter
        )

        return adapter

    @pytest.fixture
    def setup_channel_conversation(self, adapter):
        """Setup a test channel conversation"""
        def _setup():
            conversation = ConversationInfo(
                conversation_id="T12345/C12345678",
                conversation_type="channel"
            )
            adapter.conversation_manager.conversations["T12345/C12345678"] = conversation
            return conversation
        return _setup

    @pytest.fixture
    def setup_message(self, adapter):
        """Setup a test message in the cache"""
        async def _setup(conversation_id,
                         message_id="1662031200.123456",
                         reactions=None,
                         thread_id=None,
                         is_pinned=False):
            cached_msg = await adapter.conversation_manager.message_cache.add_message({
                "message_id": message_id,
                "conversation_id": conversation_id,
                "text": "Test message",
                "sender_id": "U12345678",
                "sender_name": "Slack User",
                "timestamp": int(float(message_id)),  # Convert Slack ts to ms
                "is_from_bot": False,
                "thread_id": thread_id
            })

            if reactions is not None:
                cached_msg.reactions = reactions

            if conversation_id in adapter.conversation_manager.conversations:
                adapter.conversation_manager.conversations[conversation_id].messages.add(message_id)
                if is_pinned:
                    cached_msg.is_pinned = True
                    adapter.conversation_manager.conversations[conversation_id].pinned_messages.add(message_id)

            return cached_msg
        return _setup

    @pytest.fixture
    def create_slack_message(self):
        """Create a mock Slack message"""
        def _create(message_type="channel", ts="1662031200.123456"):
            return {
                "type": "message",
                "user": "U12345678",
                "text": "Hello from Slack!",
                "ts": ts,
                "team": "T12345",
                "channel": "C12345678" if message_type == "channel" else "D12345678",
                "channel_type": message_type,
                "blocks": []
            }
        return _create

    @pytest.fixture
    def create_slack_event(self, create_slack_message):
        """Create a mock Slack event"""
        def _create(event_type="message",
                    message_type="channel",
                    with_reaction=None,
                    is_pinned=False,
                    parent_ts=None):

            if event_type == "message":
                message = create_slack_message(message_type)
                return {
                    "type": event_type,
                    "event": message
                }

            if event_type == "message_changed":
                original_message = create_slack_message(message_type)
                edited_message = create_slack_message(message_type)
                edited_message["text"] = "Edited message content"

                if is_pinned:
                    edited_message["pinned_to"] = ["C12345678"]

                return {
                    "type": "message_changed",
                    "event": {
                        "type": "message",
                        "subtype": "message_changed",
                        "channel": original_message["channel"],
                        "ts": time.time(),
                        "message": edited_message,
                        "previous_message": original_message,
                        "event_ts": time.time(),
                        "team": "T12345"
                    }
                }

            if event_type == "message_deleted":
                original_message = create_slack_message(message_type)

                return {
                    "type": "message_deleted",
                    "event": {
                        "type": "message",
                        "subtype": "message_deleted",
                        "channel": original_message["channel"],
                        "ts": time.time(),
                        "deleted_ts": original_message["ts"],
                        "event_ts": time.time(),
                        "team": "T12345",
                        "previous_message": original_message
                    }
                }

            if event_type == "reaction_added" or event_type == "reaction_removed":
                reaction = with_reaction or "thumbsup"
                message_ts = parent_ts or "1662031200.123456"

                return {
                    "type": event_type,
                    "event": {
                        "type": event_type,
                        "user": "U12345678",
                        "reaction": reaction,
                        "item": {
                            "type": "message",
                            "channel": "C12345678" if message_type == "channel" else "D12345678",
                            "ts": message_ts
                        },
                        "item_user": "U87654321",
                        "event_ts": time.time(),
                        "ts": time.time(),
                        "team": "T12345"
                    }
                }

            if event_type == "pin_added" or event_type == "pin_removed":
                message = create_slack_message(message_type)

                return {
                    "type": event_type,
                    "event": {
                        "type": event_type,
                        "user": "U12345678",
                        "channel": message["channel"],
                        "item": {
                            "type": "message",
                            "channel": message["channel"],
                            "ts": message["ts"],
                            "message": message
                        },
                        "event_ts": time.time(),
                        "ts": time.time(),
                        "team": "T12345"
                    }
                }

            if event_type == "file_share":
                message = create_slack_message(message_type, True)

                return {
                    "type": "file_share",
                    "event": {
                        "type": "message",
                        "subtype": "file_share",
                        "user": "U12345678",
                        "channel": message["channel"],
                        "ts": message["ts"],
                        "files": message["files"],
                        "event_ts": time.time(),
                        "team": "T12345"
                    }
                }

            return {}
        return _create

    # =============== TEST METHODS ===============

    @pytest.mark.asyncio
    async def test_new_message_flow(self, adapter, create_slack_event):
        """Test flow from Slack message with attachment to socket.io event"""
        event = create_slack_event(
            event_type="message",
            message_type="channel"
        )
        adapter.incoming_events_processor.downloader.download_attachments.return_value = []

        with patch.object(adapter.incoming_events_processor, "_fetch_conversation_history", return_value=[]):
            result = await adapter.incoming_events_processor.process_event(event)

            assert len(result) == 2, "Expected two events to be generated"

            assert "T12345/C12345678" in adapter.conversation_manager.conversations
            assert len(adapter.conversation_manager.conversations["T12345/C12345678"].messages) == 1

            conversation_messages = adapter.conversation_manager.message_cache.messages.get("T12345/C12345678", {})
            assert len(conversation_messages) == 1

            cached_message = next(iter(conversation_messages.values()))
            assert cached_message.text == "Hello from Slack!"
            assert cached_message.sender_id == "U12345678"

    @pytest.mark.asyncio
    async def test_edited_message_flow(self,
                                       adapter,
                                       setup_channel_conversation,
                                       setup_message,
                                       create_slack_event):
        """Test flow from Slack edited message to socket.io event"""
        setup_channel_conversation()
        await setup_message("T12345/C12345678", message_id="1662031200.123456")

        event = create_slack_event(event_type="message_changed", message_type="channel")
        result = await adapter.incoming_events_processor.process_event(event)

        assert isinstance(result, list), "Expected process_event to return a list of events"
        assert len(result) > 0, "Expected at least one event to be generated"

        assert result[0]["event_type"] == "message_updated"
        assert result[0]["data"]["conversation_id"] == "T12345/C12345678"
        assert result[0]["data"]["message_id"] == "1662031200.123456"
        assert result[0]["data"]["new_text"] == "Edited message content"

        conversation_messages = adapter.conversation_manager.message_cache.messages.get("T12345/C12345678", {})
        assert len(conversation_messages) == 1

        cached_message = next(iter(conversation_messages.values()))
        assert cached_message.text == "Edited message content"

    @pytest.mark.asyncio
    async def test_pin_message_flow(self,
                                    adapter,
                                    setup_channel_conversation,
                                    setup_message,
                                    create_slack_event):
        """Test flow from Slack pin message to socket.io event"""
        setup_channel_conversation()
        await setup_message("T12345/C12345678", message_id="1662031200.123456", is_pinned=False)

        event = create_slack_event(event_type="pin_added", message_type="channel")
        result = await adapter.incoming_events_processor.process_event(event)

        assert isinstance(result, list), "Expected process_event to return a list of events"
        assert len(result) > 0, "Expected at least one event to be generated"

        assert result[0]["event_type"] == "message_pinned"
        assert result[0]["data"]["conversation_id"] == "T12345/C12345678"
        assert result[0]["data"]["message_id"] == "1662031200.123456"

        conversation = adapter.conversation_manager.conversations["T12345/C12345678"]
        assert "1662031200.123456" in conversation.pinned_messages

        cached_message = adapter.conversation_manager.message_cache.messages["T12345/C12345678"]["1662031200.123456"]
        assert cached_message.is_pinned is True

    @pytest.mark.asyncio
    async def test_unpin_message_flow(self,
                                      adapter,
                                      setup_channel_conversation,
                                      setup_message,
                                      create_slack_event):
        """Test flow from Slack unpin message to socket.io event"""
        setup_channel_conversation()
        await setup_message("T12345/C12345678", message_id="1662031200.123456", is_pinned=True)

        event = create_slack_event(event_type="pin_removed", message_type="channel")
        result = await adapter.incoming_events_processor.process_event(event)

        assert isinstance(result, list), "Expected process_event to return a list of events"
        assert len(result) > 0, "Expected at least one event to be generated"

        assert result[0]["event_type"] == "message_unpinned"
        assert result[0]["data"]["conversation_id"] == "T12345/C12345678"
        assert result[0]["data"]["message_id"] == "1662031200.123456"

        conversation = adapter.conversation_manager.conversations["T12345/C12345678"]
        assert "1662031200.123456" not in conversation.pinned_messages

        cached_message = adapter.conversation_manager.message_cache.messages["T12345/C12345678"]["1662031200.123456"]
        assert cached_message.is_pinned is False

    @pytest.mark.asyncio
    async def test_deleted_message_flow(self,
                                        adapter,
                                        setup_channel_conversation,
                                        setup_message,
                                        create_slack_event):
        """Test flow from Slack deleted message to socket.io event"""
        setup_channel_conversation()
        await setup_message("T12345/C12345678", message_id="1662031200.123456")

        event = create_slack_event(event_type="message_deleted", message_type="channel")
        result = await adapter.incoming_events_processor.process_event(event)

        assert isinstance(result, list), "Expected process_event to return a list of events"
        assert len(result) == 1, "Expected one event to be generated"
        assert result[0]["event_type"] == "message_deleted"
        assert result[0]["data"]["conversation_id"] == "T12345/C12345678"
        assert result[0]["data"]["message_id"] == "1662031200.123456"

        conversation = adapter.conversation_manager.conversations["T12345/C12345678"]
        assert "1662031200.123456" not in adapter.conversation_manager.message_cache.messages.get("T12345/C12345678", {})
        assert len(conversation.messages) == 0

    @pytest.mark.asyncio
    async def test_added_reaction_flow(self,
                                       adapter,
                                       setup_channel_conversation,
                                       setup_message,
                                       create_slack_event):
        """Test flow from Slack added reaction to socket.io event"""
        setup_channel_conversation()
        await setup_message("T12345/C12345678", message_id="1662031200.123456")

        event = create_slack_event(event_type="reaction_added", message_type="channel", with_reaction="thumbsup")
        result = await adapter.incoming_events_processor.process_event(event)

        assert isinstance(result, list), "Expected process_event to return a list of events"
        assert len(result) == 1, "Expected one event to be generated"
        assert result[0]["event_type"] == "reaction_added"
        assert result[0]["data"]["conversation_id"] == "T12345/C12345678"
        assert result[0]["data"]["message_id"] == "1662031200.123456"
        assert result[0]["data"]["emoji"] == "thumbsup"

        cached_message = adapter.conversation_manager.message_cache.messages["T12345/C12345678"]["1662031200.123456"]
        assert "thumbsup" in cached_message.reactions, "Reaction should be added to message"
        assert cached_message.reactions["thumbsup"] == 1, "Reaction count should be 1"

    @pytest.mark.asyncio
    async def test_removed_reaction_flow(self,
                                         adapter,
                                         setup_channel_conversation,
                                         setup_message,
                                         create_slack_event):
        """Test flow from Slack removed reaction to socket.io event"""
        setup_channel_conversation()
        await setup_message("T12345/C12345678", message_id="1662031200.123456", reactions={"thumbsup": 1})

        event = create_slack_event(event_type="reaction_removed", message_type="channel", with_reaction="thumbsup")
        result = await adapter.incoming_events_processor.process_event(event)

        assert isinstance(result, list), "Expected process_event to return a list of events"
        assert len(result) == 1, "Expected one event to be generated"
        assert result[0]["event_type"] == "reaction_removed"
        assert result[0]["data"]["conversation_id"] == "T12345/C12345678"
        assert result[0]["data"]["message_id"] == "1662031200.123456"
        assert result[0]["data"]["emoji"] == "thumbsup"

        cached_message = adapter.conversation_manager.message_cache.messages["T12345/C12345678"]["1662031200.123456"]
        assert "thumbsup" not in cached_message.reactions, "Reaction should be removed from message"
