import asyncio
import discord
import os
import pytest

from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from src.adapters.discord_adapter.adapter import Adapter
from src.adapters.discord_adapter.conversation.data_classes import ConversationInfo
from src.adapters.discord_adapter.event_processing.attachment_loaders.uploader import Uploader
from src.adapters.discord_adapter.event_processing.outgoing_event_processor import OutgoingEventProcessor
from src.adapters.discord_adapter.event_processing.incoming_event_processor import IncomingEventProcessor

class TestSocketIOToDiscordFlowIntegration:
    """Integration tests for socket.io to Discord flow"""

    # =============== FIXTURES ===============

    @pytest.fixture
    def socketio_mock(self):
        """Create a mocked Socket.IO server"""
        socketio = MagicMock()
        socketio.emit_event = MagicMock()
        return socketio

    @pytest.fixture
    def discord_bot_mock(self):
        """Create a mocked Discord bot"""
        bot = AsyncMock()
        bot.user = MagicMock()
        bot.user.id = 12345678
        bot.user.name = "Test Bot"
        return bot

    @pytest.fixture
    def discord_client_mock(self, discord_bot_mock):
        """Create a mocked Discord client"""
        client = MagicMock()
        client.bot = discord_bot_mock
        client.running = True
        return client

    @pytest.fixture
    def uploader_mock(self):
        """Create a mocked Uploader"""
        uploader_mock = MagicMock(spec=Uploader)
        uploader_mock.upload_attachment = MagicMock(return_value=[])
        uploader_mock.clean_up_uploaded_files = MagicMock()
        return uploader_mock

    @pytest.fixture
    def adapter(self,
                discord_config,
                socketio_mock,
                discord_client_mock,
                uploader_mock,
                rate_limiter_mock):
        """Create a Discord adapter with mocked dependencies"""
        adapter = Adapter(discord_config, socketio_mock)
        adapter.client = discord_client_mock
        adapter.rate_limiter = rate_limiter_mock

        adapter.outgoing_events_processor = OutgoingEventProcessor(
            discord_config, discord_client_mock.bot, adapter.conversation_manager
        )
        adapter.outgoing_events_processor.uploader = uploader_mock

        adapter.incoming_events_processor = IncomingEventProcessor(
            discord_config, discord_client_mock.bot, adapter.conversation_manager
        )

        return adapter

    @pytest.fixture
    def standard_conversation_id(self):
        """Create a standard conversation ID"""
        return "discord_2SV7UT3h2SpMid0xZNcS"

    @pytest.fixture
    def setup_channel_conversation(self, adapter, standard_conversation_id):
        """Setup a test channel conversation"""
        def _setup():
            conversation = ConversationInfo(
                conversation_id=standard_conversation_id,
                platform_conversation_id="987654321/123456789",
                conversation_type="channel",
                conversation_name="general"
            )
            adapter.conversation_manager.conversations[standard_conversation_id] = conversation
            return conversation
        return _setup

    @pytest.fixture
    def setup_message(self, cache_mock, adapter):
        """Setup a test message in the cache"""
        async def _setup(conversation_id, message_id="111222333", reactions=None):
            cached_msg = await cache_mock.message_cache.add_message({
                "message_id": message_id,
                "conversation_id": conversation_id,
                "text": "Test message",
                "sender_id": "123456789",
                "sender_name": "Test User",
                "timestamp": int(datetime.now(timezone.utc).timestamp()),
                "is_from_bot": False
            })

            if reactions is not None:
                cached_msg.reactions = reactions

            if conversation_id in adapter.conversation_manager.conversations:
                adapter.conversation_manager.conversations[conversation_id].messages.add(message_id)

            return cached_msg
        return _setup

    @pytest.fixture
    def channel_mock(self):
        """Create a mocked Discord channel with proper async methods"""
        channel = AsyncMock()
        channel.send = AsyncMock(return_value=MagicMock())

        message = MagicMock()
        message.edit = AsyncMock(return_value=MagicMock())
        message.delete = AsyncMock(return_value=MagicMock())
        message.add_reaction = AsyncMock(return_value=MagicMock())
        message.remove_reaction = AsyncMock(return_value=MagicMock())
        message.pin = AsyncMock(return_value=MagicMock())
        message.unpin = AsyncMock(return_value=MagicMock())

        channel.fetch_message = AsyncMock(return_value=message)

        return channel

    # =============== TEST METHODS ===============

    @pytest.mark.asyncio
    async def test_send_message_with_attachment_flow(self,
                                                     adapter,
                                                     setup_channel_conversation,
                                                     channel_mock,
                                                     uploader_mock,
                                                     standard_conversation_id):
        """Test sending a message with an attachment"""
        setup_channel_conversation()

        mock_file = MagicMock()
        uploader_mock.upload_attachment.return_value = [[mock_file], ["tmp/test.txt"]]

        with patch.object(
            adapter.outgoing_events_processor,
            "_get_channel",
            return_value=channel_mock
        ):
            response = await adapter.outgoing_events_processor.process_event({
                "event_type": "send_message",
                "data": {
                    "conversation_id": standard_conversation_id,
                    "text": "See attachment",
                    "attachments": [
                        {
                            "file_name": "test.txt",
                            "content": "Hello from Discord!"
                        }
                    ]
                }
            })
            assert response["request_completed"] is True

            uploader_mock.upload_attachment.assert_called_once()
            uploader_mock.clean_up_uploaded_files.assert_called_once()

            channel_mock.send.assert_any_call("See attachment")
            channel_mock.send.assert_any_call(files=[mock_file])

    @pytest.mark.asyncio
    async def test_edit_message_flow(self,
                                     adapter,
                                     setup_channel_conversation,
                                     setup_message,
                                     channel_mock,
                                     standard_conversation_id):
        """Test the complete flow from socket.io edit_message to Discord call"""
        setup_channel_conversation()
        await setup_message(standard_conversation_id)

        with patch.object(
            adapter.outgoing_events_processor,
            "_get_channel",
            return_value=channel_mock
        ):
            response = await adapter.outgoing_events_processor.process_event({
                "event_type": "edit_message",
                "data": {
                    "conversation_id": standard_conversation_id,
                    "message_id": "111222333",
                    "text": "Edited message content"
                }
            })
            assert response["request_completed"] is True

            channel_mock.fetch_message.assert_called_once_with(111222333)
            message = channel_mock.fetch_message.return_value
            message.edit.assert_called_once_with(content="Edited message content")

    @pytest.mark.asyncio
    async def test_delete_message_flow(self,
                                       adapter,
                                       setup_channel_conversation,
                                       setup_message,
                                       channel_mock,
                                       standard_conversation_id):
        """Test the complete flow from socket.io delete_message to Discord call"""
        setup_channel_conversation()
        await setup_message(standard_conversation_id)

        with patch.object(
            adapter.outgoing_events_processor,
            "_get_channel",
            return_value=channel_mock
        ):
            response = await adapter.outgoing_events_processor.process_event({
                "event_type": "delete_message",
                "data": {
                    "conversation_id": standard_conversation_id,
                    "message_id": "111222333"
                }
            })
            assert response["request_completed"] is True

            channel_mock.fetch_message.assert_called_once_with(111222333)
            message = channel_mock.fetch_message.return_value
            message.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_reaction_flow(self,
                                     adapter,
                                     setup_channel_conversation,
                                     setup_message,
                                     channel_mock,
                                     standard_conversation_id):
        """Test the complete flow from socket.io add_reaction to Discord call"""
        setup_channel_conversation()
        await setup_message(standard_conversation_id)

        with patch.object(
            adapter.outgoing_events_processor,
            "_get_channel",
            return_value=channel_mock
        ):
            response = await adapter.outgoing_events_processor.process_event({
                "event_type": "add_reaction",
                "data": {
                    "conversation_id": standard_conversation_id,
                    "message_id": "111222333",
                    "emoji": "thumbs_up"
                }
            })
            assert response["request_completed"] is True

            channel_mock.fetch_message.assert_called_once_with(111222333)
            message = channel_mock.fetch_message.return_value
            message.add_reaction.assert_called_once_with("👍")

    @pytest.mark.asyncio
    async def test_remove_reaction_flow(self,
                                        adapter,
                                        setup_channel_conversation,
                                        setup_message,
                                        channel_mock,
                                        standard_conversation_id):
        """Test the complete flow from socket.io remove_reaction to Discord call"""
        setup_channel_conversation()
        await setup_message(standard_conversation_id, reactions={"thumbs_up": 1})

        with patch.object(
            adapter.outgoing_events_processor,
            "_get_channel",
            return_value=channel_mock
        ):
            response = await adapter.outgoing_events_processor.process_event({
                "event_type": "remove_reaction",
                "data": {
                    "conversation_id": standard_conversation_id,
                    "message_id": "111222333",
                    "emoji": "thumbs_up"
                }
            })
            assert response["request_completed"] is True

            channel_mock.fetch_message.assert_called_once_with(111222333)
            message = channel_mock.fetch_message.return_value
            message.remove_reaction.assert_called_once_with("👍", adapter.client.bot.user)

    @pytest.mark.asyncio
    async def test_pin_message_flow(self,
                                    adapter,
                                    setup_channel_conversation,
                                    setup_message,
                                    channel_mock,
                                    standard_conversation_id):
        """Test the complete flow from socket.io pin_message to Discord call"""
        setup_channel_conversation()
        await setup_message(standard_conversation_id)

        with patch.object(
            adapter.outgoing_events_processor,
            "_get_channel",
            return_value=channel_mock
        ):
            response = await adapter.outgoing_events_processor.process_event({
                "event_type": "pin_message",
                "data": {
                    "conversation_id": standard_conversation_id,
                    "message_id": "111222333"
                }
            })
            assert response["request_completed"] is True

            channel_mock.fetch_message.assert_called_once_with(111222333)
            message = channel_mock.fetch_message.return_value
            message.pin.assert_called_once()

    @pytest.mark.asyncio
    async def test_unpin_message_flow(self,
                                      adapter,
                                      setup_channel_conversation,
                                      setup_message,
                                      channel_mock,
                                      standard_conversation_id):
        """Test the complete flow from socket.io unpin_message to Discord call"""
        setup_channel_conversation()
        await setup_message(standard_conversation_id)

        with patch.object(
            adapter.outgoing_events_processor,
            "_get_channel",
            return_value=channel_mock
        ):
            response = await adapter.outgoing_events_processor.process_event({
                "event_type": "unpin_message",
                "data": {
                    "conversation_id": standard_conversation_id,
                    "message_id": "111222333"
                }
            })
            assert response["request_completed"] is True

            channel_mock.fetch_message.assert_called_once_with(111222333)
            message = channel_mock.fetch_message.return_value
            message.unpin.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_typing_indicator_flow(self,
                                              adapter,
                                              setup_channel_conversation,
                                              channel_mock,
                                              standard_conversation_id):
        """Test the complete flow from socket.io send_typing_indicator to Discord call"""
        setup_channel_conversation()

        with patch.object(
            adapter.outgoing_events_processor,
            "_get_channel",
            return_value=channel_mock
        ):
            response = await adapter.outgoing_events_processor.process_event({
                "event_type": "send_typing_indicator",
                "data": {
                    "conversation_id": standard_conversation_id,
                }
            })
            assert response["request_completed"] is True

            channel_mock.typing.assert_called_once()
