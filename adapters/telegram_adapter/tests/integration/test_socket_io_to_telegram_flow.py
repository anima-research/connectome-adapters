import pytest
import os
import shutil
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from telethon import functions
from telethon.tl.types import ReactionEmoji

from adapters.telegram_adapter.adapter.adapter import Adapter
from adapters.telegram_adapter.adapter.telethon_client import TelethonClient
from adapters.telegram_adapter.adapter.conversation.data_classes import ConversationInfo
from adapters.telegram_adapter.adapter.event_processors.incoming_event_processor import IncomingEventProcessor
from adapters.telegram_adapter.adapter.event_processors.outgoing_event_processor import OutgoingEventProcessor

from core.conversation.base_data_classes import UserInfo

class TestSocketIOToTelegramFlowIntegration:
    """Integration tests for socket.io to Telegram flow"""

    # =============== FIXTURES ===============

    @pytest.fixture(scope="class", autouse=True)
    def ensure_test_directories(self):
        """Create necessary test directories before tests and clean up after"""
        os.makedirs("test_attachments", exist_ok=True)
        os.makedirs("test_attachments/image", exist_ok=True)
        os.makedirs("test_attachments/document", exist_ok=True)

        yield

        if os.path.exists("test_attachments"):
            shutil.rmtree("test_attachments")

    @pytest.fixture
    def socketio_mock(self):
        """Create a mocked Socket.IO server"""
        socketio = MagicMock()
        socketio.emit = MagicMock()
        return socketio

    @pytest.fixture
    def telethon_client_mock(self):
        """Create a mocked Telethon client"""
        client = AsyncMock()
        client.client = client  # For adapter.uploader
        client.send_message = AsyncMock()
        client.edit_message = AsyncMock()
        client.delete_messages = AsyncMock()
        client.get_messages = AsyncMock()
        client.get_entity = AsyncMock()
        client.__call__ = AsyncMock()  # For reactions and other direct calls
        return client

    @pytest.fixture
    def rate_limiter_mock(self):
        """Create a mock rate limiter"""
        rate_limiter = AsyncMock()
        rate_limiter.limit_request = AsyncMock(return_value=None)
        rate_limiter.get_wait_time = AsyncMock(return_value=0)
        return rate_limiter

    @pytest.fixture
    def adapter(self, patch_config, socketio_mock, telethon_client_mock, rate_limiter_mock):
        """Create a TelegramAdapter with mocked dependencies"""
        with patch.object(TelethonClient, "__new__") as TelethonClientMock:
            TelethonClientMock.return_value = telethon_client_mock
            adapter = Adapter(patch_config, socketio_mock)
            adapter.incoming_events_processor = IncomingEventProcessor(
                patch_config, telethon_client_mock, adapter.conversation_manager
            )
            adapter.incoming_events_processor.rate_limiter = rate_limiter_mock
            adapter.outgoing_events_processor = OutgoingEventProcessor(
                patch_config, telethon_client_mock, adapter.conversation_manager
            )
            adapter.outgoing_events_processor.rate_limiter = rate_limiter_mock
            yield adapter

    @pytest.fixture
    def setup_conversation(self, adapter):
        """Setup a test conversation with a user"""
        def _setup():
            adapter.conversation_manager.conversations["456"] = ConversationInfo(
                conversation_id="456",
                conversation_type="private"
            )
            return adapter.conversation_manager.conversations["456"]
        return _setup

    @pytest.fixture
    def setup_conversation_known_member(self, adapter):
        """Setup a test conversation with a user"""
        def _setup():
            adapter.conversation_manager.conversations["456"].known_members = {
                "456": UserInfo(
                    user_id="456",
                    username="test_user",
                    first_name="Test",
                    last_name="User"
                )
            }
            return adapter.conversation_manager.conversations["456"]
        return _setup

    @pytest.fixture
    def setup_message(self, adapter):
        """Setup a test message in the cache"""
        async def _setup(reactions=None):
            cached_msg = await adapter.conversation_manager.message_cache.add_message({
                "message_id": "123",
                "conversation_id": "456",
                "text": "Test message",
                "timestamp": datetime.now()
            })

            if reactions is not None:
                cached_msg.reactions = reactions

            return cached_msg
        return _setup

    @pytest.fixture
    def create_peer_id(self):
        """Create a peer_id mock with specified user_id"""
        peer_id = MagicMock()
        peer_id.user_id = 456
        return peer_id

    @pytest.fixture
    def create_message_response(self, create_peer_id):
        """Create a mock message response from Telethon"""
        def _create(text = "Test message", with_reactions=False, reactions_list=[]):
            message = MagicMock()
            message.id = "123"
            message.message = text
            message.date = datetime.now()
            message.peer_id = create_peer_id

            if with_reactions:
                reaction_results = []
                reactions_to_add = reactions_list

                for emoji, count in reactions_to_add:
                    reaction = MagicMock()
                    reaction.reaction = MagicMock()
                    reaction.reaction.emoticon = emoji
                    reaction.count = count
                    reaction_results.append(reaction)

                reactions = MagicMock()
                reactions.results = reaction_results
                message.reactions = reactions

            return message
        return _create

    # =============== TEST METHODS ===============

    @pytest.mark.asyncio
    async def test_send_message_flow(self, adapter, telethon_client_mock, create_message_response):
        """Test the complete flow from socket.io send_message to Telethon call"""
        entity = MagicMock()
        telethon_client_mock.get_entity.return_value = entity
        telethon_client_mock.send_message.return_value = create_message_response(text="Hello, world!")

        assert len(adapter.conversation_manager.conversations) == 0
        assert len(adapter.conversation_manager.message_cache.messages) == 0

        response = await adapter.outgoing_events_processor.process_event(
            "send_message",
            {
                "conversation_id": "456",
                "text": "Hello, world!",
                "thread_id": None
            }
        )
        assert response["request_completed"] is True
        assert response["message_ids"] == ["123"]

        telethon_client_mock.get_entity.assert_called_once()
        telethon_client_mock.send_message.assert_called_once_with(
            entity=entity,
            message="Hello, world!",
            reply_to=None
        )

        assert len(adapter.conversation_manager.conversations) == 1
        assert "456" in adapter.conversation_manager.conversations
        assert adapter.conversation_manager.conversations["456"].conversation_type == "private"

        assert len(adapter.conversation_manager.message_cache.messages) == 1
        assert "456" in adapter.conversation_manager.message_cache.messages
        assert "123" in adapter.conversation_manager.message_cache.messages["456"]

        cached_message = adapter.conversation_manager.message_cache.messages["456"]["123"]
        assert cached_message.text == "Hello, world!"
        assert cached_message.conversation_id == "456"

    @pytest.mark.asyncio
    async def test_edit_message_flow(self,
                                     adapter,
                                     telethon_client_mock,
                                     setup_conversation,
                                     setup_conversation_known_member,
                                     setup_message,
                                     create_message_response):
        """Test the complete flow from socket.io edit_message to Telethon call"""
        entity = MagicMock()
        telethon_client_mock.get_entity.return_value = entity

        setup_conversation()
        setup_conversation_known_member()
        await setup_message()
        telethon_client_mock.edit_message.return_value = create_message_response(
            text="Edited message content"
        )

        response = await adapter.outgoing_events_processor.process_event(
            "edit_message",
            {
                "conversation_id": "456",
                "message_id": "123",
                "text": "Edited message content"
            }
        )
        assert response["request_completed"] is True

        telethon_client_mock.get_entity.assert_called_once()
        telethon_client_mock.edit_message.assert_called_once_with(
            entity=entity,
            message=123,
            text="Edited message content"
        )

        assert adapter.conversation_manager.message_cache.messages["456"]["123"].text == "Edited message content"

        conversation = adapter.conversation_manager.conversations["456"]
        assert conversation.conversation_type == "private"

    @pytest.mark.asyncio
    async def test_delete_message_flow(self,
                                       adapter,
                                       telethon_client_mock,
                                       setup_conversation,
                                       setup_conversation_known_member,
                                       setup_message):
        """Test the complete flow from socket.io delete_message to Telethon call"""
        entity = MagicMock()
        telethon_client_mock.get_entity.return_value = entity

        setup_conversation()
        setup_conversation_known_member()
        await setup_message()
        telethon_client_mock.delete_messages.return_value = [MagicMock()]

        response = await adapter.outgoing_events_processor.process_event(
            "delete_message",
            {
                "conversation_id": "456",
                "message_id": "123"
            }
        )
        assert response["request_completed"] is True

        telethon_client_mock.get_entity.assert_called_once()
        telethon_client_mock.delete_messages.assert_called_once_with(
            entity=entity,
            message_ids=[123]
        )

        assert "123" not in adapter.conversation_manager.message_cache.messages.get("456", {})

    @pytest.mark.asyncio
    async def test_add_reaction_flow(self,
                                     adapter,
                                     telethon_client_mock,
                                     setup_conversation,
                                     setup_conversation_known_member,
                                     setup_message,
                                     create_message_response):
        """Test the complete flow from socket.io add_reaction to Telethon call"""
        entity = MagicMock()
        telethon_client_mock.get_entity.return_value = entity

        with patch(
                 "adapters.telegram_adapter.adapter.event_processors.outgoing_event_processor.functions"
             ) as mock_functions, \
             patch(
                 "adapters.telegram_adapter.adapter.event_processors.outgoing_event_processor.ReactionEmoji"
             ) as mock_reaction_emoji:

            mock_reaction_emoji.return_value = MagicMock()
            mock_send_reaction_request = MagicMock()
            mock_functions.messages.SendReactionRequest.return_value = mock_send_reaction_request

            setup_conversation()
            setup_conversation_known_member()
            await setup_message()
            telethon_client_mock.return_value = create_message_response(
                with_reactions=True,
                reactions_list=[("👍", 1)]
            )

            response = await adapter.outgoing_events_processor.process_event(
                "add_reaction",
                {
                    "conversation_id": "456",
                    "message_id": "123",
                    "emoji": "👍"
                }
            )
            assert response["request_completed"] is True

            mock_reaction_emoji.assert_called_once_with(emoticon="👍")
            mock_functions.messages.SendReactionRequest.assert_called_once()
            call_args = mock_functions.messages.SendReactionRequest.call_args[1]
            assert call_args["peer"] == entity
            assert call_args["msg_id"] == 123
            assert len(call_args["reaction"]) == 1

            telethon_client_mock.assert_called_once_with(mock_send_reaction_request)

            cached_message = adapter.conversation_manager.message_cache.messages["456"]["123"]
            assert "👍" in cached_message.reactions
            assert cached_message.reactions["👍"] == 1

    @pytest.mark.asyncio
    async def test_remove_reaction_flow(self,
                                        adapter,
                                        telethon_client_mock,
                                        setup_conversation,
                                        setup_conversation_known_member,
                                        setup_message,
                                        create_message_response):
        """Test the complete flow from socket.io remove_reaction to Telethon call"""
        entity = MagicMock()
        telethon_client_mock.get_entity.return_value = entity

        with patch(
                 "adapters.telegram_adapter.adapter.event_processors.outgoing_event_processor.functions"
             ) as mock_functions, \
             patch(
                 "adapters.telegram_adapter.adapter.event_processors.outgoing_event_processor.ReactionEmoji"
             ) as mock_reaction_emoji:

            mock_reaction_emoji.return_value = MagicMock()
            mock_send_reaction_request = MagicMock()
            mock_functions.messages.SendReactionRequest.return_value = mock_send_reaction_request

            setup_conversation()
            setup_conversation_known_member()
            await setup_message(reactions={"👍": 1})
            telethon_client_mock.get_messages.return_value = create_message_response(
                with_reactions=True,
                reactions_list=[("👍", 1)]
            )
            telethon_client_mock.return_value = create_message_response(
                reactions_list=[]  # Empty reactions
            )

            response = await adapter.outgoing_events_processor.process_event(
                "remove_reaction",
                {
                    "conversation_id": "456",
                    "message_id": "123",
                    "emoji": "👍"
                }
            )
            assert response["request_completed"] is True

            telethon_client_mock.get_entity.assert_called_once()
            telethon_client_mock.get_messages.assert_called_once_with(entity, ids=123)

            mock_functions.messages.SendReactionRequest.assert_called_once()
            call_args = mock_functions.messages.SendReactionRequest.call_args[1]
            assert call_args["peer"] == entity
            assert call_args["msg_id"] == 123
            assert len(call_args["reaction"]) == 0  # Empty array means remove all reactions

            telethon_client_mock.assert_called_once_with(mock_send_reaction_request)

            cached_message = adapter.conversation_manager.message_cache.messages["456"]["123"]
            assert "👍" not in cached_message.reactions
            assert len(cached_message.reactions) == 0
