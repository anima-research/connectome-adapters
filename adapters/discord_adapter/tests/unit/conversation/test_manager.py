import pytest
import asyncio
import os
import shutil
import discord
from datetime import datetime

from unittest.mock import AsyncMock, MagicMock, patch

from adapters.discord_adapter.adapter.conversation.data_classes import ConversationInfo
from adapters.discord_adapter.adapter.conversation.manager import Manager, DiscordEventType
from adapters.discord_adapter.adapter.conversation.thread_handler import ThreadHandler
from adapters.discord_adapter.adapter.conversation.user_builder import UserBuilder
from adapters.discord_adapter.adapter.conversation.reaction_handler import ReactionHandler

from core.cache.message_cache import MessageCache, CachedMessage
from core.cache.attachment_cache import AttachmentCache
from core.conversation.base_data_classes import ThreadInfo, UserInfo, ConversationDelta

class TestManager:
    """Tests for the Discord conversation manager class"""

    @pytest.fixture(scope="class", autouse=True)
    def ensure_test_directories(self):
        """Create necessary test directories before tests and clean up after"""
        os.makedirs("test_attachments", exist_ok=True)
        os.makedirs("test_attachments/document", exist_ok=True)

        yield

        if os.path.exists("test_attachments"):
            shutil.rmtree("test_attachments")

    @pytest.fixture
    def manager(self, patch_config):
        """Create a Manager with mocked dependencies"""
        with patch.object(MessageCache, "get_message_by_id", return_value=MagicMock(spec=MessageCache)), \
             patch.object(AttachmentCache, "add_attachment", return_value=MagicMock(spec=AttachmentCache)):

            manager = Manager(patch_config)
            manager.message_cache = AsyncMock(spec=MessageCache)
            manager.attachment_cache = AsyncMock(spec=AttachmentCache)
            return manager

    @pytest.fixture
    def user_info_mock(self):
        """Create a mock UserInfo"""
        return UserInfo(
            user_id="123456789",
            username="Discord User",
            is_bot=False
        )

    @pytest.fixture
    def conversation_info_mock(self):
        """Create a mock ConversationInfo"""
        return ConversationInfo(
            conversation_id="987654321/123456789",
            conversation_type="channel",
            conversation_name="general",
            messages=set(["111222333"])
        )

    @pytest.fixture
    def cached_message_mock(self):
        """Create a mock cached message"""
        return CachedMessage(
            message_id="111222333",
            conversation_id="987654321/123456789",
            thread_id=None,
            sender_id="123456789",
            sender_name="Discord User",
            text="Hello world!",
            timestamp=1609459200000,  # 2021-01-01 in ms
            is_from_bot=False,
            reactions={"+1": 1},
            is_pinned=False
        )

    @pytest.fixture
    def mock_discord_message(self):
        """Create a mock Discord message"""
        message = MagicMock(spec=discord.Message)
        message.id = 111222333
        message.content = "Hello world!"
        created_at = datetime(2021, 1, 1, 12, 0, 0)
        message.created_at = created_at

        # Set up channel
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 123456789
        channel.name = "general"
        message.channel = channel

        # Set up guild
        guild = MagicMock(spec=discord.Guild)
        guild.id = 987654321
        message.guild = guild

        # Set up author
        author = MagicMock()
        author.id = 123456789
        author.name = "Discord User"
        message.author = author

        return message

    @pytest.fixture
    def mock_discord_edited_message(self):
        """Create a mock Discord edited message event"""
        message = MagicMock()
        message.message_id = 111222333
        message.channel_id = 123456789
        message.guild_id = 987654321
        message.data = {
            "content": "Hello world! (edited)",
            "edited_timestamp": "2021-01-01T12:30:00.000000+00:00",
            "pinned": False
        }
        return message

    @pytest.fixture
    def mock_discord_deleted_message(self):
        """Create a mock Discord edited message event"""
        message = MagicMock()
        message.message_id = 111222333
        message.channel_id = 123456789
        message.guild_id = 987654321
        return message

    @pytest.fixture
    def mock_discord_reaction_event(self):
        """Create a mock Discord reaction event"""
        event = {
            "event_type": DiscordEventType.ADDED_REACTION,
            "message": MagicMock()
        }
        event["message"].message_id = 111222333
        event["message"].channel_id = 123456789
        event["message"].guild_id = 987654321
        event["message"].emoji = MagicMock()
        event["message"].emoji.name = "🔥"
        return event

    @pytest.fixture
    def attachment_mock(self):
        """Create a mock attachment"""
        return {
            "attachment_id": "abc123",
            "filename": "abc123.jpg",
            "content_type": "image/jpeg",
            "content": None,
            "url": "https://discord.com/attachments/abc123.jpg",
            "size": 12345,
            "processable": True
        }

    class TestGetOrCreateConversation:
        """Tests for conversation creation and identification"""

        @pytest.mark.asyncio
        async def test_get_or_create_conversation_info_new(self, manager, mock_discord_message):
            """Test creating a new conversation"""
            assert len(manager.conversations) == 0
            conversation_info = await manager._get_or_create_conversation_info(mock_discord_message)

            assert len(manager.conversations) == 1
            assert conversation_info.conversation_id == "987654321/123456789"
            assert conversation_info.conversation_type == "channel"
            assert conversation_info.conversation_name == "general"
            assert conversation_info.just_started is True

        @pytest.mark.asyncio
        async def test_get_or_create_conversation_info_existing(self, manager, mock_discord_message):
            """Test getting an existing conversation"""
            with patch.object(manager, "_get_conversation_id", return_value="987654321/123456789"):
                manager.conversations["987654321/123456789"] = ConversationInfo(
                    conversation_id="987654321/123456789",
                    conversation_type="channel",
                    conversation_name="general"
                )

                conversation_info = await manager._get_or_create_conversation_info(mock_discord_message)

                assert len(manager.conversations) == 1
                assert conversation_info.conversation_id == "987654321/123456789"
                assert conversation_info.conversation_type == "channel"

    class TestAddToConversation:
        """Tests for add_to_conversation method"""

        @pytest.mark.asyncio
        async def test_add_message(self,
                                   manager,
                                   mock_discord_message,
                                   cached_message_mock,
                                   user_info_mock,
                                   attachment_mock):
            """Test adding a message with attachment"""
            thread_info = ThreadInfo(
                thread_id="111222333",
                root_message_id="111222333"
            )

            with patch.object(manager, "_get_or_create_conversation_info",
                             return_value=ConversationInfo(
                                conversation_id="987654321/123456789",
                                conversation_type="channel",
                                conversation_name="general",
                                just_started=True
                             )), \
                 patch.object(UserBuilder, "add_user_info_to_conversation", return_value=user_info_mock), \
                 patch.object(ThreadHandler, "add_thread_info", return_value=thread_info), \
                 patch.object(manager, "_create_message", return_value=cached_message_mock), \
                 patch.object(manager, "_update_attachment", return_value=[attachment_mock]):

                delta = await manager.add_to_conversation({
                    "message": mock_discord_message,
                    "attachments": [attachment_mock]
                })

                assert delta["conversation_id"] == "987654321/123456789"
                assert delta["fetch_history"] is True  # New conversation should fetch history

                assert len(delta["added_messages"]) == 1
                assert delta["added_messages"][0]["message_id"] == "111222333"
                assert delta["added_messages"][0]["attachments"] == [attachment_mock]

        @pytest.mark.asyncio
        async def test_add_empty_message(self, manager):
            """Test adding an empty message"""
            assert not await manager.add_to_conversation({})

    class TestUpdateConversation:
        """Tests for update_conversation method"""

        @pytest.mark.asyncio
        async def test_update_nonexistent_conversation(self, manager, mock_discord_edited_message):
            """Test updating a non-existent conversation"""
            assert not await manager.update_conversation({
                "event_type": DiscordEventType.EDITED_MESSAGE,
                "message": mock_discord_edited_message
            })

        @pytest.mark.asyncio
        async def test_update_message_content(self,
                                              manager,
                                              conversation_info_mock,
                                              cached_message_mock,
                                              mock_discord_edited_message):
            """Test updating a message's content"""
            manager.message_cache.get_message_by_id.return_value = cached_message_mock
            manager.conversations["987654321/123456789"] = conversation_info_mock

            delta = await manager.update_conversation({
                "event_type": DiscordEventType.EDITED_MESSAGE,
                "message": mock_discord_edited_message
            })

            assert delta["conversation_id"] == "987654321/123456789"
            assert delta["updated_messages"][0]["message_id"] == "111222333"
            assert cached_message_mock.text == mock_discord_edited_message.data["content"]

        @pytest.mark.asyncio
        async def test_pin_message(self,
                                   manager,
                                   cached_message_mock,
                                   conversation_info_mock,
                                   mock_discord_edited_message):
            """Test pinning a message"""
            manager.message_cache.get_message_by_id.return_value = cached_message_mock
            manager.conversations["987654321/123456789"] = conversation_info_mock

            mock_discord_edited_message.data["content"] = cached_message_mock.text
            mock_discord_edited_message.data["pinned"] = True

            delta = await manager.update_conversation({
                "event_type": DiscordEventType.EDITED_MESSAGE,
                "message": mock_discord_edited_message
            })

            assert delta["conversation_id"] == "987654321/123456789"
            assert len(delta["pinned_message_ids"]) == 1
            assert delta["pinned_message_ids"][0] == cached_message_mock.message_id

            assert cached_message_mock.is_pinned is True
            assert cached_message_mock.message_id in conversation_info_mock.pinned_messages

        @pytest.mark.asyncio
        async def test_unpin_message(self,
                                     manager,
                                     cached_message_mock,
                                     conversation_info_mock,
                                     mock_discord_edited_message):
            """Test unpinning a message"""
            cached_message_mock.is_pinned = True
            conversation_info_mock.pinned_messages.add(cached_message_mock.message_id)
            manager.message_cache.get_message_by_id.return_value = cached_message_mock
            manager.conversations["987654321/123456789"] = conversation_info_mock

            mock_discord_edited_message.data["content"] = cached_message_mock.text
            mock_discord_edited_message.data["pinned"] = False

            delta = await manager.update_conversation({
                "event_type": DiscordEventType.EDITED_MESSAGE,
                "message": mock_discord_edited_message
            })

            assert delta["conversation_id"] == "987654321/123456789"
            assert len(delta["unpinned_message_ids"]) == 1
            assert delta["unpinned_message_ids"][0] == cached_message_mock.message_id

            assert cached_message_mock.is_pinned is False
            assert cached_message_mock.message_id not in conversation_info_mock.pinned_messages

        @pytest.mark.asyncio
        async def test_update_message_reaction(self,
                                               manager,
                                               conversation_info_mock,
                                               cached_message_mock,
                                               mock_discord_reaction_event):
            """Test updating a message's reactions"""
            manager.message_cache.get_message_by_id.return_value = cached_message_mock
            manager.conversations["987654321/123456789"] = conversation_info_mock

            delta = await manager.update_conversation(mock_discord_reaction_event)

            assert delta["conversation_id"] == "987654321/123456789"
            assert delta["added_reactions"] == ["fire"]
            assert "fire" in cached_message_mock.reactions
            assert cached_message_mock.reactions["fire"] == 1

    class TestDeleteFromConversation:
        """Tests for delete_from_conversation method"""

        @pytest.mark.asyncio
        async def test_delete_message(self,
                                      manager,
                                      conversation_info_mock,
                                      cached_message_mock,
                                      mock_discord_deleted_message):
            """Test deleting a message"""
            manager.conversations["987654321/123456789"] = conversation_info_mock
            manager.message_cache.get_message_by_id.return_value = cached_message_mock
            manager.message_cache.delete_message.return_value = True

            with patch.object(ThreadHandler, "remove_thread_info"):
                delta = await manager.delete_from_conversation(
                    incoming_event=mock_discord_deleted_message
                )

                manager.message_cache.get_message_by_id.assert_called_with(
                    conversation_id="987654321/123456789",
                    message_id="111222333"
                )
                manager.message_cache.delete_message.assert_called_with(
                    "987654321/123456789", "111222333"
                )

                assert delta["conversation_id"] == "987654321/123456789"
                assert "111222333" in delta["deleted_message_ids"]
