import asyncio
import discord
import os
import pytest
import shutil
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from adapters.discord_adapter.adapter.adapter import Adapter
from adapters.discord_adapter.adapter.discord_client import DiscordClient
from adapters.discord_adapter.adapter.attachment_loaders.uploader import Uploader
from adapters.discord_adapter.adapter.attachment_loaders.downloader import Downloader
from adapters.discord_adapter.adapter.conversation.data_classes import ConversationInfo
from adapters.discord_adapter.adapter.event_processors.outgoing_event_processor import OutgoingEventProcessor
from adapters.discord_adapter.adapter.event_processors.incoming_event_processor import IncomingEventProcessor
from core.conversation.base_data_classes import UserInfo

class TestDiscordToSocketIOFlowIntegration:
    """Integration tests for Discord to socket.io flow"""

    # =============== FIXTURES ===============

    @pytest.fixture(scope="class", autouse=True)
    def ensure_test_directories(self):
        """Create necessary test directories before tests and clean up after"""
        os.makedirs("test_attachments", exist_ok=True)
        os.makedirs("test_attachments/image", exist_ok=True)

        yield

        if os.path.exists("test_attachments"):
            shutil.rmtree("test_attachments")

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
    def downloader_mock(self):
        """Create a mocked Downloader"""
        downloader_mock = AsyncMock()
        downloader_mock.download_attachment = AsyncMock(return_value=[])
        return downloader_mock

    @pytest.fixture
    def rate_limiter_mock(self):
        """Create a mock rate limiter"""
        rate_limiter = AsyncMock()
        rate_limiter.limit_request = AsyncMock(return_value=None)
        rate_limiter.get_wait_time = AsyncMock(return_value=0)
        return rate_limiter

    @pytest.fixture
    def adapter(self,
                patch_config,
                socketio_mock,
                discord_client_mock,
                downloader_mock,
                rate_limiter_mock):
        """Create a Discord adapter with mocked dependencies"""
        adapter = Adapter(patch_config, socketio_mock)
        adapter.client = discord_client_mock
        adapter.rate_limiter = rate_limiter_mock

        adapter.outgoing_events_processor = OutgoingEventProcessor(
            patch_config, discord_client_mock.bot, adapter.conversation_manager
        )
        adapter.incoming_events_processor = IncomingEventProcessor(
            patch_config, discord_client_mock.bot, adapter.conversation_manager
        )
        adapter.incoming_events_processor.rate_limiter = rate_limiter_mock
        adapter.incoming_events_processor.downloader = downloader_mock

        return adapter

    @pytest.fixture
    def setup_channel_conversation(self, adapter):
        """Setup a test channel conversation"""
        def _setup():
            conversation = ConversationInfo(
                conversation_id="987654321/123456789",
                conversation_type="channel",
                conversation_name="general"
            )
            adapter.conversation_manager.conversations["987654321/123456789"] = conversation
            return conversation
        return _setup

    @pytest.fixture
    def setup_message(self, adapter):
        """Setup a test message in the cache"""
        async def _setup(conversation_id,
                         message_id="111222333",
                         reactions=None,
                         thread_id=None,
                         is_pinned=False):
            cached_msg = await adapter.conversation_manager.message_cache.add_message({
                "message_id": message_id,
                "conversation_id": conversation_id,
                "text": "Test message",
                "sender_id": "123456789",
                "sender_name": "Test User",
                "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
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
    def create_discord_message(self):
        """Create a mock Discord message"""
        def _create(message_type="channel", with_attachment=False, with_reply=False, is_pinned=False):
            message = MagicMock(spec=discord.Message)
            message.id = 111222333
            message.content = "Hello from Discord!"
            message.created_at = datetime.now(timezone.utc)
            message.type = discord.MessageType.default
            message.pinned = is_pinned

            # Create author
            author = MagicMock()
            author.id = 123456789
            author.name = "Discord User"
            author.display_name = "Cool User"
            message.author = author

            if message_type == "dm":
                # DM channel
                channel = MagicMock(spec=discord.DMChannel)
                channel.id = 123456789
                message.guild = None
            else:
                # Regular text channel
                channel = MagicMock(spec=discord.TextChannel)
                channel.id = 123456789
                channel.name = "general"

                # Guild
                guild = MagicMock(spec=discord.Guild)
                guild.id = 987654321
                message.guild = guild

            message.channel = channel

            # Add attachment if requested
            if with_attachment:
                attachment = MagicMock(spec=discord.Attachment)
                attachment.id = 444555666
                attachment.filename = "test.jpg"
                attachment.url = "https://discord.com/attachments/test.jpg"
                attachment.content_type = "image/jpeg"
                attachment.size = 12345
                message.attachments = [attachment]
            else:
                message.attachments = []

            # Add reply reference if requested
            if with_reply:
                ref = MagicMock()
                ref.message_id = 999888777
                message.reference = ref
            else:
                message.reference = None

            return message
        return _create

    @pytest.fixture
    def create_discord_event(self, create_discord_message):
        """Create a mock Discord event"""
        def _create(event_type="new_message",
                    message_type="channel",
                    with_attachment=False,
                    with_reply=False,
                    with_emoji=None,
                    is_pinned=False):

            if event_type == "new_message":
                return {
                    "type": "new_message",
                    "event": create_discord_message(
                        message_type, with_attachment, with_reply, is_pinned
                    )
                }

            if event_type == "edited_message":
                payload = MagicMock()
                payload.message_id = 111222333
                payload.channel_id = 123456789
                payload.guild_id = 987654321 if message_type == "channel" else None
                payload.data = {
                    "content": "Edited message content",
                    "edited_timestamp": datetime.now(timezone.utc).isoformat(),
                    "pinned": is_pinned
                }
                return {
                    "type": "edited_message",
                    "event": payload
                }

            if event_type == "deleted_message":
                payload = MagicMock()
                payload.message_id = 111222333
                payload.channel_id = 123456789
                payload.guild_id = 987654321 if message_type == "channel" else None
                return {
                    "type": "deleted_message",
                    "event": payload
                }

            if event_type == "added_reaction" or event_type == "removed_reaction":
                payload = MagicMock()
                payload.message_id = 111222333
                payload.channel_id = 123456789
                payload.guild_id = 987654321 if message_type == "channel" else None
                payload.emoji = MagicMock()
                payload.emoji.name = with_emoji or "👍"
                return {
                    "type": event_type,
                    "event": payload
                }

            return {}
        return _create

    # =============== TEST METHODS ===============

    @pytest.mark.asyncio
    async def test_receive_message_with_attachment_flow(self, adapter, create_discord_event):
        """Test flow from Discord message with attachment to socket.io event"""
        event = create_discord_event(
            event_type="new_message",
            message_type="channel",
            with_attachment=True
        )
        attachment_result = [{
            "attachment_id": "discord_4567",
            "attachment_type": "image",
            "filename": "discord_4567.jpg",
            "size": 12345,
            "content_type": "image/jpeg",
            "content": "Hello from Discord!",
            "url": "https://discord.com/attachments/test.jpg",
            "created_at": datetime.now(timezone.utc),
            "processable": True
        }]
        adapter.incoming_events_processor.downloader.download_attachment.return_value = attachment_result

        with patch.object(adapter.incoming_events_processor, "_fetch_conversation_history", return_value=[]):
            result = await adapter.incoming_events_processor.process_event(event)

            assert len(result) == 2, "Expected two event to be generated"
            assert "attachments" in result[1]["data"]
            assert len(result[1]["data"]["attachments"]) == 1

            assert "987654321/123456789" in adapter.conversation_manager.conversations
            assert len(adapter.conversation_manager.conversations["987654321/123456789"].messages) == 1

            conversation_messages = adapter.conversation_manager.message_cache.messages.get("987654321/123456789", {})
            assert len(conversation_messages) == 1

            cached_message = next(iter(conversation_messages.values()))
            assert cached_message.text == "Hello from Discord!"
            assert cached_message.sender_id == "123456789"

            cached_attachments = adapter.conversation_manager.attachment_cache.attachments
            assert len(cached_attachments) == 1
            assert "discord_4567" in cached_attachments
            assert cached_attachments["discord_4567"].attachment_id == "discord_4567"
            assert cached_attachments["discord_4567"].attachment_type == "image"
            assert cached_attachments["discord_4567"].filename == "discord_4567.jpg"
            assert cached_attachments["discord_4567"].size == 12345
            assert cached_attachments["discord_4567"].content_type == "image/jpeg"
            assert cached_attachments["discord_4567"].url == "https://discord.com/attachments/test.jpg"
            assert cached_attachments["discord_4567"].processable is True

    @pytest.mark.asyncio
    async def test_edited_message_flow(self,
                                       adapter,
                                       setup_channel_conversation,
                                       setup_message,
                                       create_discord_event):
        """Test flow from Discord edited message to socket.io event"""
        setup_channel_conversation()
        await setup_message("987654321/123456789", message_id="111222333")

        event = create_discord_event(event_type="edited_message", message_type="channel")
        result = await adapter.incoming_events_processor.process_event(event)

        assert isinstance(result, list), "Expected process_event to return a list of events"
        assert len(result) > 0, "Expected at least one event to be generated"

        assert result[0]["event_type"] == "message_updated"
        assert result[0]["data"]["conversation_id"] == "987654321/123456789"
        assert result[0]["data"]["message_id"] == "111222333"
        assert result[0]["data"]["new_text"] == "Edited message content"

        conversation_messages = adapter.conversation_manager.message_cache.messages.get("987654321/123456789", {})
        assert len(conversation_messages) == 1

        cached_message = next(iter(conversation_messages.values()))
        assert cached_message.text == "Edited message content"

    @pytest.mark.asyncio
    async def test_pin_message_flow(self,
                                    adapter,
                                    setup_channel_conversation,
                                    setup_message,
                                    create_discord_event):
        """Test flow from Discord pin message to socket.io event"""
        setup_channel_conversation()
        await setup_message("987654321/123456789", message_id="111222333", is_pinned=False)

        event = create_discord_event(event_type="edited_message", message_type="channel", is_pinned=True)
        result = await adapter.incoming_events_processor.process_event(event)

        assert isinstance(result, list), "Expected process_event to return a list of events"
        assert len(result) == 2, "Expected two events to be generated: message update and pin"

        update_event = [e for e in result if e["event_type"] == "message_updated"][0]
        assert update_event["data"]["conversation_id"] == "987654321/123456789"
        assert update_event["data"]["message_id"] == "111222333"

        pin_event = [e for e in result if e["event_type"] == "message_pinned"][0]
        assert pin_event["data"]["conversation_id"] == "987654321/123456789"
        assert pin_event["data"]["message_id"] == "111222333"

        conversation = adapter.conversation_manager.conversations["987654321/123456789"]
        assert "111222333" in conversation.pinned_messages

        cached_message = adapter.conversation_manager.message_cache.messages["987654321/123456789"]["111222333"]
        assert cached_message.is_pinned is True

    @pytest.mark.asyncio
    async def test_unpin_message_flow(self,
                                      adapter,
                                      setup_channel_conversation,
                                      setup_message,
                                      create_discord_event):
        """Test flow from Discord unpin message to socket.io event"""
        setup_channel_conversation()
        await setup_message("987654321/123456789", message_id="111222333", is_pinned=True)

        event = create_discord_event(event_type="edited_message", message_type="channel", is_pinned=False)
        result = await adapter.incoming_events_processor.process_event(event)

        assert isinstance(result, list), "Expected process_event to return a list of events"
        assert len(result) == 2, "Expected two events to be generated: message update and unpin"

        update_event = [e for e in result if e["event_type"] == "message_updated"][0]
        assert update_event["data"]["conversation_id"] == "987654321/123456789"
        assert update_event["data"]["message_id"] == "111222333"

        unpin_event = [e for e in result if e["event_type"] == "message_unpinned"][0]
        assert unpin_event["data"]["conversation_id"] == "987654321/123456789"
        assert unpin_event["data"]["message_id"] == "111222333"

        conversation = adapter.conversation_manager.conversations["987654321/123456789"]
        assert "111222333" not in conversation.pinned_messages

        cached_message = adapter.conversation_manager.message_cache.messages["987654321/123456789"]["111222333"]
        assert cached_message.is_pinned is False

    @pytest.mark.asyncio
    async def test_deleted_message_flow(self,
                                        adapter,
                                        setup_channel_conversation,
                                        setup_message,
                                        create_discord_event):
        """Test flow from Discord deleted message to socket.io event"""
        setup_channel_conversation()
        await setup_message("987654321/123456789", message_id="111222333")

        event = create_discord_event(event_type="deleted_message", message_type="channel")
        result = await adapter.incoming_events_processor.process_event(event)

        assert isinstance(result, list), "Expected process_event to return a list of events"
        assert len(result) == 1, "Expected one event to be generated"
        assert result[0]["event_type"] == "message_deleted"
        assert result[0]["data"]["conversation_id"] == "987654321/123456789"
        assert result[0]["data"]["message_id"] == "111222333"

        conversation = adapter.conversation_manager.conversations["987654321/123456789"]
        assert "111222333" not in adapter.conversation_manager.message_cache.messages.get("987654321/123456789", {})
        assert len(conversation.messages) == 0

    @pytest.mark.asyncio
    async def test_added_reaction_flow(self,
                                       adapter,
                                       setup_channel_conversation,
                                       setup_message,
                                       create_discord_event):
        """Test flow from Discord added reaction to socket.io event"""
        setup_channel_conversation()
        await setup_message("987654321/123456789", message_id="111222333")

        event = create_discord_event(event_type="added_reaction", message_type="channel", with_emoji="👍")
        result = await adapter.incoming_events_processor.process_event(event)

        assert isinstance(result, list), "Expected process_event to return a list of events"
        assert len(result) == 1, "Expected one event to be generated"
        assert result[0]["event_type"] == "reaction_added"
        assert result[0]["data"]["conversation_id"] == "987654321/123456789"
        assert result[0]["data"]["message_id"] == "111222333"
        assert result[0]["data"]["emoji"] == "thumbs_up"

        cached_message = adapter.conversation_manager.message_cache.messages["987654321/123456789"]["111222333"]
        assert "thumbs_up" in cached_message.reactions, "Reaction should be added to message"
        assert cached_message.reactions["thumbs_up"] == 1, "Reaction count should be 1"

    @pytest.mark.asyncio
    async def test_removed_reaction_flow(self,
                                         adapter,
                                         setup_channel_conversation,
                                         setup_message,
                                         create_discord_event):
        """Test flow from Discord removed reaction to socket.io event"""
        setup_channel_conversation()
        await setup_message("987654321/123456789", message_id="111222333", reactions={"thumbs_up": 1})

        event = create_discord_event(event_type="removed_reaction", message_type="channel", with_emoji="👍")
        result = await adapter.incoming_events_processor.process_event(event)

        assert isinstance(result, list), "Expected process_event to return a list of events"
        assert len(result) == 1, "Expected one event to be generated"
        assert result[0]["event_type"] == "reaction_removed"
        assert result[0]["data"]["conversation_id"] == "987654321/123456789"
        assert result[0]["data"]["message_id"] == "111222333"
        assert result[0]["data"]["emoji"] == "thumbs_up"

        cached_message = adapter.conversation_manager.message_cache.messages["987654321/123456789"]["111222333"]
        assert "thumbs_up" not in cached_message.reactions, "Reaction should be removed from message"
