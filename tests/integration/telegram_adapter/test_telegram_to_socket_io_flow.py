import os
import pytest

from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from telethon import functions
from telethon.tl.types import ReactionEmoji

from src.adapters.telegram_adapter.adapter import Adapter
from src.adapters.telegram_adapter.conversation.data_classes import ConversationInfo
from src.adapters.telegram_adapter.event_processors.incoming_event_processor import IncomingEventProcessor
from src.adapters.telegram_adapter.event_processors.outgoing_event_processor import OutgoingEventProcessor

class TestTelegramToSocketIOFlowIntegration:
    """Integration tests for Telegram to socket.io flow"""

    # =============== FIXTURES ===============

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
        client.get_entity = AsyncMock()
        return client

    @pytest.fixture
    def rate_limiter_mock(self):
        """Create a mock rate limiter"""
        rate_limiter = AsyncMock()
        rate_limiter.limit_request = AsyncMock(return_value=None)
        rate_limiter.get_wait_time = AsyncMock(return_value=0)
        return rate_limiter

    @pytest.fixture
    def adapter(self, telegram_config, socketio_mock, telethon_client_mock, rate_limiter_mock):
        """Create a TelegramAdapter with mocked dependencies"""
        adapter = Adapter(telegram_config, socketio_mock)
        adapter.client = telethon_client_mock
        adapter.incoming_events_processor = IncomingEventProcessor(
            telegram_config, telethon_client_mock, adapter.conversation_manager
        )
        adapter.incoming_events_processor.rate_limiter = rate_limiter_mock
        adapter.outgoing_events_processor = OutgoingEventProcessor(
            telegram_config, telethon_client_mock, adapter.conversation_manager
        )
        adapter.outgoing_events_processor.rate_limiter = rate_limiter_mock
        return adapter

    @pytest.fixture
    def setup_conversation(self, adapter):
        """Setup a test conversation"""
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
                "456": {
                    "user_id": "456",
                    "username": "test_user",
                    "first_name": "Test",
                    "last_name": "User"
                }
            }
            return adapter.conversation_manager.conversations["456"]
        return _setup

    @pytest.fixture
    def setup_message(self, adapter):
        """Setup a test message in the cache"""
        async def _setup(message_id="123", reactions=None, is_pinned=False):
            cached_msg = await adapter.conversation_manager.message_cache.add_message({
                "message_id": message_id,
                "conversation_id": "456",
                "text": "Test message",
                "timestamp": int(datetime.now().timestamp()),
                "sender_id": "456",
                "sender_name": "Test User",
                "is_from_bot": False
            })

            if reactions is not None:
                cached_msg.reactions = reactions
            cached_msg.is_pinned = is_pinned

            return cached_msg
        return _setup

    @pytest.fixture
    def create_telethon_message(self):
        """Create a mock Telethon message"""
        def _create(text="Test message", with_reactions=False, reactions_list=[]):
            message = MagicMock()
            message.id = "123"
            message.message = text
            message.date = datetime.now()

            peer_id = MagicMock()
            peer_id.user_id = 456
            message.peer_id = peer_id

            message.media = None

            if with_reactions:
                reaction_results = []
                for emoji, count in reactions_list:
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

    @pytest.fixture
    def create_telethon_user(self):
        """Create a mock Telethon user"""
        class UserMock:
            def __init__(self):
                self.id = 456
                self.username = "testuser"
                self.first_name = "Test"
                self.last_name = "User"
                self.bot = False
        return UserMock

    @pytest.fixture
    def create_telethon_event(self, create_telethon_message, create_telethon_user):
        """Create a mock Telethon event"""
        def _create(event_type,
                    message=None,
                    user=None,
                    deleted_ids=None,
                    channel_id=None,
                    with_reactions=False,
                    reactions_list=None):

            event = MagicMock()

            if message is None and event_type not in ["deleted_message"]:
                message = create_telethon_message(
                    with_reactions=with_reactions, reactions_list=reactions_list
                )

            if user is None and event_type not in ["deleted_message"]:
                user = create_telethon_user()

            if event_type == "deleted_message":
                event.deleted_ids = deleted_ids or [123, 456]
                event.channel_id = channel_id or 456
            else:
                event.message = message

            return event, user
        return _create

    @pytest.fixture
    def create_pin_action_event(self):
        """Create a mock pin message event"""
        def _create(message_id="123"):
            event = MagicMock()
            message = MagicMock()

            action = MagicMock()
            action.__class__.__name__ = "MessageActionPinMessage"
            message.action = action

            reply_to = MagicMock()
            reply_to.reply_to_msg_id = message_id
            message.reply_to = reply_to

            peer_id = MagicMock()
            peer_id.user_id = 456
            message.peer_id = peer_id

            message.date = datetime.now()
            event.action_message = message

            return event
        return _create

    @pytest.fixture
    def create_unpin_action_event(self):
        """Create a mock unpin message event"""
        def _create(message_id="123"):
            event = MagicMock()
            event.action_message = None
            event.new_pin = True
            event.unpin = True

            original_update = MagicMock()
            original_update.messages = [int(message_id)]  # Make sure it's an int
            original_update.pinned = False  # False indicates unpinned
            original_update.__class__.__name__ = "UpdatePinnedMessages"

            peer = MagicMock()
            peer.user_id = 456
            original_update.peer = peer
            original_update.peer_id = None

            event.original_update = original_update
            return event
        return _create

    # =============== TEST METHODS ===============
    @pytest.mark.asyncio
    async def test_receive_message_flow(self,
                                        adapter,
                                        telethon_client_mock,
                                        create_telethon_event):
        """Test flow from Telegram new_message to socket.io message_received"""
        event, user = create_telethon_event("new_message")
        telethon_client_mock.get_entity.return_value = user
        result = await adapter.incoming_events_processor.process_event({
            "type": "new_message",
            "event": event
        })

        assert isinstance(result, list), "Expected process_event to return a list of events"
        assert len(result) > 0, "Expected at least one event to be generated"

        print(result)

        message_events = [evt for evt in result if evt.get("event_type") == "message_received"]
        assert len(message_events) == 1, "Expected one message_received event"

        message_event = message_events[0]
        assert message_event["adapter_type"] == "telegram"
        assert message_event["event_type"] == "message_received"
        assert message_event["data"]["conversation_id"] == "456"
        assert message_event["data"]["message_id"] == "123"
        assert message_event["data"]["text"] == "Test message"

        assert "456" in adapter.conversation_manager.message_cache.messages
        assert "123" in adapter.conversation_manager.message_cache.messages["456"]
        assert adapter.conversation_manager.message_cache.messages["456"]["123"].text == "Test message"

    @pytest.mark.asyncio
    async def test_edit_message_flow(self,
                                     adapter,
                                     telethon_client_mock,
                                     setup_conversation,
                                     setup_conversation_known_member,
                                     setup_message,
                                     create_telethon_event):
        """Test flow from Telegram edited_message to internal event"""
        setup_conversation()
        setup_conversation_known_member()
        await setup_message()

        event, user = create_telethon_event("edited_message")
        event.message.message = "Edited message text"
        telethon_client_mock.get_entity.return_value = user

        result = await adapter.incoming_events_processor.process_event({
            "type": "edited_message",
            "event": event
        })

        assert isinstance(result, list), "Expected process_event to return a list of events"
        assert len(result) > 0, "Expected at least one event to be generated"

        updated_events = [evt for evt in result if evt.get("event_type") == "message_updated"]
        assert len(updated_events) == 1, "Expected one message_updated event"

        updated_event = updated_events[0]
        assert updated_event["adapter_type"] == "telegram"
        assert updated_event["event_type"] == "message_updated"
        assert updated_event["data"]["conversation_id"] == "456"
        assert updated_event["data"]["message_id"] == "123"
        assert updated_event["data"]["new_text"] == "Edited message text"

        assert adapter.conversation_manager.message_cache.messages["456"]["123"].text == "Edited message text"

    @pytest.mark.asyncio
    async def test_delete_message_flow(self,
                                       adapter,
                                       setup_conversation,
                                       setup_conversation_known_member,
                                       setup_message,
                                       create_telethon_event):
        """Test flow from Telegram deleted_message to internal event"""
        setup_conversation()
        setup_conversation_known_member()
        await setup_message(message_id="123")
        await setup_message(message_id="456")

        event, _ = create_telethon_event("deleted_message", deleted_ids=[123, 456], channel_id=456)
        result = await adapter.incoming_events_processor.process_event({
            "type": "deleted_message",
            "event": event
        })

        assert isinstance(result, list), "Expected process_event to return a list of events"
        assert len(result) == 2, "Expected two events for two deleted messages"

        for event_data in result:
            assert event_data["adapter_type"] == "telegram"
            assert event_data["event_type"] == "message_deleted"
            assert event_data["data"]["conversation_id"] == "456"
            assert event_data["data"]["message_id"] in ["123", "456"]

        assert "123" not in adapter.conversation_manager.message_cache.messages.get("456", {})
        assert "456" not in adapter.conversation_manager.message_cache.messages.get("456", {})

    @pytest.mark.asyncio
    async def test_message_pinned_flow(self, adapter,
                                       setup_conversation,
                                       setup_conversation_known_member,
                                       setup_message,
                                       create_pin_action_event):
        """Test flow from Telegram pin action to internal event"""
        setup_conversation()
        setup_conversation_known_member()
        await setup_message()

        event = create_pin_action_event()
        result = await adapter.incoming_events_processor.process_event({
            "type": "chat_action",
            "event": event
        })

        assert isinstance(result, list), "Expected process_event to return a list of events"
        assert len(result) > 0, "Expected at least one event to be generated"

        pin_events = [evt for evt in result if evt.get("event_type") == "message_pinned"]
        assert len(pin_events) == 1, "Expected one message_pinned event"

        pin_event = pin_events[0]
        assert pin_event["adapter_type"] == "telegram"
        assert pin_event["event_type"] == "message_pinned"
        assert pin_event["data"]["conversation_id"] == "456"
        assert pin_event["data"]["message_id"] == "123"

        assert adapter.conversation_manager.message_cache.messages["456"]["123"].is_pinned is True
        assert "123" in adapter.conversation_manager.conversations["456"].pinned_messages

    @pytest.mark.asyncio
    async def test_message_unpinned_flow(self, adapter,
                                         setup_conversation,
                                         setup_conversation_known_member,
                                         setup_message,
                                         create_unpin_action_event):
        """Test flow from Telegram unpin action to internal event"""
        setup_conversation()
        setup_conversation_known_member()
        await setup_message(is_pinned=True)
        adapter.conversation_manager.conversations["456"].pinned_messages.add("123")

        event = create_unpin_action_event()
        result = await adapter.incoming_events_processor.process_event({
            "type": "chat_action",
            "event": event
        })

        assert isinstance(result, list), "Expected process_event to return a list of events"
        assert len(result) > 0, "Expected at least one event to be generated"

        unpin_events = [evt for evt in result if evt.get("event_type") == "message_unpinned"]
        assert len(unpin_events) == 1, "Expected one message_unpinned event"

        unpin_event = unpin_events[0]
        assert unpin_event["adapter_type"] == "telegram"
        assert unpin_event["event_type"] == "message_unpinned"
        assert unpin_event["data"]["conversation_id"] == "456"
        assert unpin_event["data"]["message_id"] == "123"

        assert adapter.conversation_manager.message_cache.messages["456"]["123"].is_pinned is False
        assert "123" not in adapter.conversation_manager.conversations["456"].pinned_messages

    @pytest.mark.asyncio
    async def test_reaction_added_flow(self,
                                       adapter,
                                       telethon_client_mock,
                                       setup_conversation,
                                       setup_conversation_known_member,
                                       setup_message,
                                       create_telethon_event):
        """Test flow from Telegram edited_message with reactions to socket.io reaction_added"""
        setup_conversation()
        setup_conversation_known_member()
        await setup_message(reactions={})

        event, user = create_telethon_event(
            "edited_message",
            with_reactions=True,
            reactions_list=[("👍", 1)]
        )
        event.message.message = "Test message"
        telethon_client_mock.get_entity.return_value = user

        result = await adapter.incoming_events_processor.process_event({
            "type": "edited_message",
            "event": event
        })

        assert isinstance(result, list), "Expected process_event to return a list of events"
        assert len(result) > 0, "Expected at least one event to be generated"

        reaction_events = [evt for evt in result if evt.get("event_type") == "reaction_added"]
        assert len(reaction_events) == 1, "Expected one reaction_added event"

        event_data = reaction_events[0]
        assert event_data["adapter_type"] == "telegram"
        assert event_data["event_type"] == "reaction_added"
        assert event_data["data"]["conversation_id"] == "456"
        assert event_data["data"]["message_id"] == "123"
        assert event_data["data"]["emoji"] == "thumbs_up"

        cached_message = adapter.conversation_manager.message_cache.messages["456"]["123"]
        assert "thumbs_up" in cached_message.reactions
        assert cached_message.reactions["thumbs_up"] == 1

    @pytest.mark.asyncio
    async def test_reaction_removed_flow(self,
                                         adapter,
                                         telethon_client_mock,
                                         setup_conversation,
                                         setup_conversation_known_member,
                                         setup_message,
                                         create_telethon_event):
        """Test flow from Telegram edited_message with removed reactions to socket.io reaction_removed"""
        setup_conversation()
        setup_conversation_known_member()
        await setup_message(reactions={"thumbs_up": 1, "red_heart": 1})

        event, user = create_telethon_event(
            "edited_message",
            with_reactions=True,
            reactions_list=[("👍", 1)]
        )
        event.message.message = "Test message"
        telethon_client_mock.get_entity.return_value = user

        result = await adapter.incoming_events_processor.process_event({
            "type": "edited_message",
            "event": event
        })

        assert isinstance(result, list), "Expected process_event to return a list of events"
        assert len(result) > 0, "Expected at least one event to be generated"

        reaction_events = [evt for evt in result if evt.get("event_type") == "reaction_removed"]
        assert len(reaction_events) == 1, "Expected one reaction_removed event"

        event_data = reaction_events[0]
        assert event_data["adapter_type"] == "telegram"
        assert event_data["event_type"] == "reaction_removed"
        assert event_data["data"]["conversation_id"] == "456"
        assert event_data["data"]["message_id"] == "123"
        assert event_data["data"]["emoji"] == "red_heart"

        cached_message = adapter.conversation_manager.message_cache.messages["456"]["123"]
        assert "thumbs_up" in cached_message.reactions
        assert "red_heart" not in cached_message.reactions
