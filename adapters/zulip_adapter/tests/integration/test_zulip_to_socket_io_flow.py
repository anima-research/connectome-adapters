import emoji
import os
import pytest
import shutil

from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from adapters.zulip_adapter.adapter.adapter import Adapter
from adapters.zulip_adapter.adapter.zulip_client import ZulipClient
from adapters.zulip_adapter.adapter.attachment_loaders.uploader import Uploader
from adapters.zulip_adapter.adapter.conversation.data_classes import ConversationInfo
from adapters.zulip_adapter.adapter.event_processors.incoming_event_processor import IncomingEventProcessor
from adapters.zulip_adapter.adapter.event_processors.outgoing_event_processor import OutgoingEventProcessor
from core.conversation.base_data_classes import UserInfo

class TestZulipToSocketIOFlowIntegration:
    """Integration tests for Zulip to socket.io flow"""

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
    def zulip_client_mock(self):
        """Create a mocked Zulip client"""
        client = MagicMock()
        client.api_key = "test_api_key"
        client.get_messages = MagicMock()
        return client

    @pytest.fixture
    def downloader_mock(self):
        """Create a mocked Downloader"""
        downloader_mock = AsyncMock()
        downloader_mock.download_attachment = AsyncMock(return_value=[])
        return downloader_mock

    @pytest.fixture
    def adapter(self, patch_config, socketio_mock, zulip_client_mock, downloader_mock):
        """Create a ZulipAdapter with mocked dependencies"""
        with patch.object(ZulipClient, "__new__", return_value=zulip_client_mock), \
             patch.object(Uploader, "__new__", return_value=AsyncMock()) as uploader_mock:

            adapter = Adapter(patch_config, socketio_mock)
            adapter.client = zulip_client_mock

            adapter.outgoing_events_processor = OutgoingEventProcessor(
                patch_config, zulip_client_mock, adapter.conversation_manager
            )
            adapter.outgoing_events_processor.uploader = uploader_mock

            adapter.incoming_events_processor = IncomingEventProcessor(
                patch_config, zulip_client_mock, adapter.conversation_manager
            )
            adapter.incoming_events_processor.downloader = downloader_mock

            yield adapter

    @pytest.fixture
    def setup_private_conversation(self, adapter):
        """Setup a test private conversation"""
        def _setup():
            conversation = ConversationInfo(
                conversation_id="101_102",
                conversation_type="private",
                known_members={
                    "101": UserInfo(user_id="101", username="Test User", email="test@example.com"),
                    "102": UserInfo(user_id="102", username="Bot User", email="bot@example.com")
                }
            )
            adapter.conversation_manager.conversations["101_102"] = conversation
            return conversation
        return _setup

    @pytest.fixture
    def setup_stream_conversation(self, adapter):
        """Setup a test stream conversation"""
        def _setup():
            conversation = ConversationInfo(
                conversation_id="201/Test Topic",
                conversation_type="stream",
                conversation_name="Test Stream"
            )
            adapter.conversation_manager.conversations["201/Test Topic"] = conversation
            return conversation
        return _setup

    @pytest.fixture
    def setup_message(self, adapter):
        """Setup a test message in the cache"""
        async def _setup(conversation_id, message_id="12345", reactions=None):
            cached_msg = await adapter.conversation_manager.message_cache.add_message({
                "message_id": message_id,
                "conversation_id": conversation_id,
                "text": "Test message",
                "sender_id": "102",
                "sender_name": "Test User 2",
                "timestamp": int(datetime.now().timestamp() * 1000),
                "is_from_bot": False
            })

            if reactions is not None:
                cached_msg.reactions = reactions

            if conversation_id in adapter.conversation_manager.conversations:
                adapter.conversation_manager.conversations[conversation_id].messages.add(message_id)

            return cached_msg
        return _setup

    @pytest.fixture
    def create_zulip_message(self):
        """Create a mock Zulip message"""
        def _create(message_type="private", with_attachment=False, with_reaction=False):
            message = {
                "id": 12345,
                "sender_id": 102,
                "sender_full_name": "Test User 2",
                "sender_email": "test2@example.com",
                "content": "Hello, world!",
                "timestamp": int(datetime.now().timestamp())
            }

            if message_type == "private":
                message["type"] = "private"
                message["display_recipient"] = [
                    {"id": 101, "email": "test@example.com", "full_name": "Test User"},
                    {"id": 102, "email": "test2@example.com", "full_name": "Test User 2"}
                ]
            else:  # stream message
                message["type"] = "stream"
                message["stream_id"] = 201
                message["subject"] = "Test Topic"
                message["display_recipient"] = "Test Stream"

            if with_attachment:
                message["content"] = "Look at this: [image.jpg](/user_uploads/image.jpg)"

            if with_reaction:
                message["reaction"] = {
                    "user_id": 102,
                    "emoji_name": "thumbs_up",
                    "emoji_code": "1f44d",
                    "reaction_type": "unicode_emoji",
                    "message_id": 12345
                }

            return message
        return _create

    @pytest.fixture
    def create_zulip_event(self, create_zulip_message):
        """Create a mock Zulip event"""
        def _create(event_type="message", message_type="private", with_attachment=False, with_reaction=False):
            if event_type == "message":
                return {
                    "type": "message",
                    "message": create_zulip_message(message_type, with_attachment)
                }

            if event_type == "update_message":
                return {
                    "type": "update_message",
                    "message_id": 12345,
                    "content": "Updated message content",
                    "edit_timestamp": int(datetime.now().timestamp()),
                }

            if event_type == "delete_message":
                return {
                    "type": "delete_message",
                    "message_type": message_type,
                    "message_id": 12345,
                }

            if event_type == "reaction":
                return {
                    "type": "reaction",
                    "message_id": 12345,
                    "user_id": 102,
                    "emoji_name": "thumbs_up",
                    "emoji_code": "1f44d",
                    "reaction_type": "unicode_emoji",
                    "op": "add"  # or "remove"
                }

            return {}
        return _create

    # =============== TEST METHODS ===============

    @pytest.mark.asyncio
    async def test_receive_private_message_flow(self, adapter, create_zulip_event):
        """Test flow from Zulip private message to socket.io event"""
        event = create_zulip_event(event_type="message", message_type="private")
        result = await adapter.incoming_events_processor.process_event(event)

        assert isinstance(result, list), "Expected _handle_message to return a list of events"
        assert len(result) > 0, "Expected at least one event to be generated"

        assert "101_102" in adapter.conversation_manager.conversations
        assert adapter.conversation_manager.conversations["101_102"].conversation_type == "private"

        conversation_messages = adapter.conversation_manager.message_cache.messages.get("101_102", {})
        assert len(conversation_messages) == 1

        cached_message = next(iter(conversation_messages.values()))
        assert cached_message.text == "Hello, world!"
        assert cached_message.sender_id == "102"

    @pytest.mark.asyncio
    async def test_receive_stream_message_flow(self, adapter, create_zulip_event):
        """Test flow from Zulip stream message to socket.io event"""
        event = create_zulip_event(event_type="message", message_type="stream")
        result = await adapter.incoming_events_processor.process_event(event)

        assert isinstance(result, list), "Expected _handle_message to return a list of events"
        assert len(result) > 0, "Expected at least one event to be generated"

        assert "201/Test Topic" in adapter.conversation_manager.conversations
        assert adapter.conversation_manager.conversations["201/Test Topic"].conversation_type == "stream"

        conversation_messages = adapter.conversation_manager.message_cache.messages.get("201/Test Topic", {})
        assert len(conversation_messages) == 1

        cached_message = next(iter(conversation_messages.values()))
        assert cached_message.text == "Hello, world!"
        assert cached_message.sender_id == "102"

    @pytest.mark.asyncio
    async def test_receive_message_with_attachment_flow(self, adapter, create_zulip_event):
        """Test flow from Zulip message with attachment to socket.io event"""
        adapter.incoming_events_processor.downloader.download_attachment.return_value = [{
            "attachment_id": "abc123",
            "attachment_type": "image",
            "file_extension": "jpg",
            "created_at": datetime.now(),
            "size": 12345
        }]

        event = create_zulip_event(event_type="message", message_type="private", with_attachment=True)
        result = await adapter.incoming_events_processor.process_event(event)

        assert isinstance(result, list), "Expected _handle_message to return a list of events"
        assert len(result) > 0, "Expected at least one event to be generated"

        message_events = [e for e in result if e.get("event_type") == "message_received"]
        assert len(message_events) == 1, "Expected one message_received event"

        message_event = message_events[0]
        assert "attachments" in message_event["data"]
        assert len(message_event["data"]["attachments"]) == 1
        assert message_event["data"]["attachments"][0]["attachment_id"] == "abc123"

    @pytest.mark.asyncio
    async def test_update_message_flow(self, adapter, setup_private_conversation, setup_message, create_zulip_event):
        """Test flow from Zulip message update to socket.io event"""
        setup_private_conversation()
        await setup_message("101_102", message_id="12345")

        event = create_zulip_event(event_type="update_message")
        result = await adapter.incoming_events_processor.process_event(event)

        assert isinstance(result, list), "Expected _handle_update_message to return a list of events"
        assert len(result) > 0, "Expected at least one event to be generated"

        update_events = [e for e in result if e.get("event_type") == "message_updated"]
        assert len(update_events) == 1, "Expected one message_updated event"

        update_event = update_events[0]
        assert update_event["data"]["message_id"] == "12345"
        assert update_event["data"]["conversation_id"] == "101_102"
        assert update_event["data"]["new_text"] == "Updated message content"

        cached_message = adapter.conversation_manager.message_cache.messages["101_102"]["12345"]
        assert cached_message.text == "Updated message content"

    @pytest.mark.asyncio
    async def test_delete_message_flow(self, adapter, setup_private_conversation, setup_message, create_zulip_event):
        """Test flow from Zulip message update to socket.io event"""
        setup_private_conversation()
        await setup_message("101_102", message_id="12345")

        event = create_zulip_event(event_type="delete_message")
        result = await adapter.incoming_events_processor.process_event(event)

        assert isinstance(result, list), "Expected _handle_delete_message to return a list of events"
        assert len(result) > 0, "Expected at least one event to be generated"

        delete_events = [e for e in result if e.get("event_type") == "message_deleted"]
        assert len(delete_events) == 1, "Expected one message_deleted event"

        delete_event = delete_events[0]
        assert delete_event["data"]["message_id"] == "12345"
        assert delete_event["data"]["conversation_id"] == "101_102"

    @pytest.mark.asyncio
    async def test_add_reaction_flow(self, adapter, setup_private_conversation, setup_message, create_zulip_event):
        """Test flow from Zulip add reaction to socket.io event"""
        setup_private_conversation()
        await setup_message("101_102", message_id="12345")

        event = create_zulip_event(event_type="reaction")
        event["op"] = "add"
        result = await adapter.incoming_events_processor.process_event(event)

        assert isinstance(result, list), "Expected _handle_reaction to return a list of events"
        assert len(result) > 0, "Expected at least one event to be generated"

        reaction_events = [e for e in result if e.get("event_type") == "reaction_added"]
        assert len(reaction_events) == 1, "Expected one reaction_added event"

        reaction_event = reaction_events[0]
        assert reaction_event["data"]["message_id"] == "12345"
        assert reaction_event["data"]["conversation_id"] == "101_102"
        assert reaction_event["data"]["emoji"] == "👍"  # Should convert from name to Unicode

        cached_message = adapter.conversation_manager.message_cache.messages["101_102"]["12345"]
        assert "👍" in cached_message.reactions
        assert cached_message.reactions["👍"] == 1

    @pytest.mark.asyncio
    async def test_remove_reaction_flow(self, adapter, setup_private_conversation, setup_message, create_zulip_event):
        """Test flow from Zulip remove reaction to socket.io event"""
        setup_private_conversation()
        await setup_message("101_102", message_id="12345", reactions={"👍": 1, "👎": 1})

        event = create_zulip_event(event_type="reaction")
        event["op"] = "remove"
        result = await adapter.incoming_events_processor.process_event(event)

        assert isinstance(result, list), "Expected _handle_reaction to return a list of events"
        assert len(result) > 0, "Expected at least one event to be generated"

        reaction_events = [e for e in result if e.get("event_type") == "reaction_removed"]
        assert len(reaction_events) == 1, "Expected one reaction_removed event"

        reaction_event = reaction_events[0]
        assert reaction_event["data"]["message_id"] == "12345"
        assert reaction_event["data"]["conversation_id"] == "101_102"
        assert reaction_event["data"]["emoji"] == "👍"  # Should convert from name to Unicode

        cached_message = adapter.conversation_manager.message_cache.messages["101_102"]["12345"]
        assert "👍" not in cached_message.reactions
        assert "👎" in cached_message.reactions
        assert cached_message.reactions["👎"] == 1
