import asyncio
import os
import pytest

from unittest.mock import AsyncMock, MagicMock, patch

from src.adapters.zulip_adapter.conversation.data_classes import ConversationInfo
from src.adapters.zulip_adapter.conversation.manager import Manager, ZulipEventType
from src.adapters.zulip_adapter.conversation.thread_handler import ThreadHandler
from src.adapters.zulip_adapter.conversation.user_builder import UserBuilder

from src.core.cache.message_cache import MessageCache, CachedMessage
from src.core.cache.attachment_cache import AttachmentCache
from src.core.conversation.base_data_classes import ThreadInfo, UserInfo
from src.core.utils.emoji_converter import EmojiConverter

class TestManager:
    """Tests for the Zulip conversation manager class"""

    @pytest.fixture
    def manager(self, zulip_config):
        """Create a Manager with mocked dependencies"""
        message_mock = MagicMock(spec=CachedMessage)
        message_mock.attachments = set()  # Empty set of attachments

        with patch.object(MessageCache, "get_message_by_id", return_value=MagicMock(spec=MessageCache)), \
            patch.object(AttachmentCache, "add_attachment", return_value=MagicMock(spec=AttachmentCache)):

            manager = Manager(zulip_config)
            manager.message_cache = AsyncMock(spec=MessageCache)
            manager.message_cache.get_message_by_id.return_value = message_mock
            manager.attachment_cache = AsyncMock(spec=AttachmentCache)
            return manager

    @pytest.fixture
    def user_info_mock(self):
        """Create a mock UserInfo"""
        return UserInfo(user_id="101", username="Test User", email="test@example.com")

    @pytest.fixture
    def standard_private_conversation_id(self):
        """Create a standard private conversation ID"""
        return "zulip_T8PioprYxwVr5Dv7HYMJ"

    @pytest.fixture
    def conversation_info_mock(self, standard_private_conversation_id):
        """Create a mock ConversationInfo"""
        return ConversationInfo(
            platform_conversation_id="101_102",
            conversation_id=standard_private_conversation_id,
            conversation_type="private",
            messages=set(["12346"])
        )

    @pytest.fixture
    def private_message_mock(self):
        """Create a mock Zulip private message"""
        return {
            "id": 12346,
            "sender_id": 102,
            "sender_full_name": "Test User 2",
            "sender_email": "test@example.com",
            "content": "@_**Test User|101** [said](https://zulip.com/identifiers/12345):\n```quote\nHello, world!\n```\nHello!",
            "timestamp": 1609459200,  # 2021-01-01
            "type": "private",
            "display_recipient": [
                {"id": 101, "email": "test@example.com", "full_name": "Test User"},
                {"id": 102, "email": "test2@example.com", "full_name": "Test User 2"}
            ]
        }

    @pytest.fixture
    def cached_private_message_mock(self, standard_private_conversation_id):
        """Create a mock cached private message"""
        return CachedMessage(
            message_id="12346",
            conversation_id=standard_private_conversation_id,
            thread_id="12345",
            sender_id="102",
            sender_name="Test User 2",
            text="Hello!",
            timestamp=1609459200,
            edit_timestamp=None,
            edited=False,
            is_from_bot=False
        )

    class TestGetOrCreateConversation:
        """Tests for conversation creation and identification"""

        @pytest.fixture
        def stream_message_mock(self):
            """Create a mock Zulip stream message"""
            return {
                "id": 12346,
                "sender_id": 101,
                "sender_full_name": "Test User",
                "sender_email": "test@example.com",
                "content": "Hello, stream!",
                "timestamp": 1609459300,
                "type": "stream",
                "stream_id": 201,
                "subject": "Test Topic",
                "display_recipient": "Test Stream"
            }

        @pytest.fixture
        def standard_stream_conversation_id(self):
            """Create a standard stream conversation ID"""
            return "zulip_lAqfjVSRHht3MtFoVO09"

        @pytest.mark.asyncio
        async def test_get_conversation_id_private(self,
                                                   manager,
                                                   private_message_mock):
            """Test getting conversation ID for private message"""
            conversation_id = await manager._get_platform_conversation_id(private_message_mock)
            assert conversation_id == "101_102"

        @pytest.mark.asyncio
        async def test_get_conversation_id_stream(self,
                                                  manager,
                                                  stream_message_mock):
            """Test getting conversation ID for stream message"""
            conversation_id = await manager._get_platform_conversation_id(stream_message_mock)
            assert conversation_id == "201/Test Topic"

        @pytest.mark.asyncio
        async def test_get_conversation_id_invalid(self, manager):
            """Test getting conversation ID for invalid message"""
            assert await manager._get_platform_conversation_id({}) is None

        @pytest.mark.asyncio
        async def test_get_or_create_conversation_info_new(self,
                                                           manager,
                                                           stream_message_mock,
                                                           standard_stream_conversation_id):
            """Test creating a new conversation"""
            assert len(manager.conversations) == 0
            conversation_info = await manager._get_or_create_conversation_info(
                {"message": stream_message_mock}
            )

            assert len(manager.conversations) == 1
            assert conversation_info.conversation_id == standard_stream_conversation_id
            assert conversation_info.conversation_type == "stream"
            assert conversation_info.just_started is True

        @pytest.mark.asyncio
        async def test_get_or_create_conversation_info_existing(self,
                                                                manager,
                                                                private_message_mock,
                                                                standard_private_conversation_id):
            """Test getting an existing conversation"""
            await manager._get_or_create_conversation_info({
                "message": private_message_mock
            })
            conversation_info = await manager._get_or_create_conversation_info({
                "message": private_message_mock
            })

            assert len(manager.conversations) == 1
            assert conversation_info.conversation_id == standard_private_conversation_id
            assert conversation_info.conversation_type == "private"

    class TestAddToConversation:
        """Tests for add_to_conversation method"""

        @pytest.fixture
        def attachment_mock(self):
            """Create a mock attachment"""
            return {
                "attachment_id": "abc123",
                "filename": "abc123.jpg",
                "size": 12345,
                "content_type": "image/jpeg",
                "content": "test content",
                "url": "https://zulip.com/user_uploads/1/ab/abc123/test.jpg",
                "processable": True
            }

        @pytest.mark.asyncio
        async def test_add_message(self,
                                   manager,
                                   private_message_mock,
                                   cached_private_message_mock,
                                   user_info_mock,
                                   attachment_mock,
                                   standard_private_conversation_id):
            """Test adding a private message with attachment"""
            thread_info = ThreadInfo(thread_id="12346", root_message_id="12346")

            with patch.object(UserBuilder, "add_user_info_to_conversation", return_value=user_info_mock), \
                 patch.object(ThreadHandler, "add_thread_info", return_value=thread_info), \
                 patch.object(manager, "_create_message", return_value=cached_private_message_mock) as mock_create_message, \
                 patch.object(manager, "_update_attachment", return_value=[attachment_mock]):

                delta = await manager.add_to_conversation({
                    "message": private_message_mock,
                    "attachments": [attachment_mock]
                })

                assert delta["conversation_id"] == standard_private_conversation_id
                assert delta["fetch_history"] is True  # New conversation should fetch history

                assert len(delta["added_messages"]) == 1
                assert delta["added_messages"][0]["message_id"] == "12346"
                assert delta["added_messages"][0]["thread_id"] == "12345"
                assert delta["added_messages"][0]["attachments"] == [attachment_mock]

                mock_create_message.assert_called_once()

        @pytest.mark.asyncio
        async def test_add_empty_message(self, manager):
            """Test adding an empty message"""
            assert await manager.add_to_conversation({}) == {}

    class TestUpdateConversation:
        """Tests for update_conversation method"""

        @pytest.fixture
        def edited_message_mock(self):
            """Create a mock Zulip edited message event"""
            return {
                "message_id": 12346,
                "content": "Hello! (edited)",
                "timestamp": 1609459500,
                "edit_timestamp": 1609459500
            }

        @pytest.fixture
        def reaction_message_mock(self):
            """Create a mock Zulip reaction event"""
            return {
                "message_id": 12346,
                "user_id": 101,
                "emoji_name": "thumbs_up",
                "emoji_code": "1f44d",
                "reaction_type": "unicode_emoji",
                "op": "add"
            }

        @pytest.mark.asyncio
        async def test_update_message_content(self,
                                              manager,
                                              conversation_info_mock,
                                              cached_private_message_mock,
                                              edited_message_mock,
                                              standard_private_conversation_id):
            """Test updating a message's content"""
            manager.message_cache.get_message_by_id.return_value = cached_private_message_mock
            manager.conversations[standard_private_conversation_id] = conversation_info_mock

            with patch.object(ThreadHandler, "update_thread_info", return_value=(False, None)):
                delta = await manager.update_conversation({
                    "event_type": ZulipEventType.UPDATE_MESSAGE,
                    "message": edited_message_mock
                })

                assert delta["conversation_id"] == standard_private_conversation_id

                assert len(delta["updated_messages"]) == 1
                assert delta["updated_messages"][0]["message_id"] == "12346"
                assert delta["updated_messages"][0]["text"] == "Hello! (edited)"
                assert cached_private_message_mock.text == "Hello! (edited)"

        @pytest.mark.asyncio
        async def test_update_message_reaction(self,
                                              manager,
                                              conversation_info_mock,
                                              cached_private_message_mock,
                                              reaction_message_mock,
                                              standard_private_conversation_id):
            """Test updating a message's reactions"""
            manager.message_cache.get_message_by_id.return_value = cached_private_message_mock
            manager.conversations[standard_private_conversation_id] = conversation_info_mock

            instance_mock = MagicMock()
            instance_mock.platform_specific_to_standard.return_value = "thumbs_up"

            with patch.object(EmojiConverter, "_instance", instance_mock):
                delta = await manager.update_conversation({
                    "event_type": ZulipEventType.REACTION,
                    "message": reaction_message_mock
                })

                assert delta["conversation_id"] == standard_private_conversation_id
                assert delta["message_id"] == "12346"

                assert len(delta["added_reactions"]) == 1
                assert delta["added_reactions"][0] == "thumbs_up"

                assert len(cached_private_message_mock.reactions) == 1
                assert cached_private_message_mock.reactions["thumbs_up"] == 1

        @pytest.mark.asyncio
        async def test_update_nonexistent_message(self, manager, edited_message_mock):
            """Test updating a non-existent message"""
            manager.message_cache.get_message_by_id.return_value = None

            assert await manager.update_conversation({
                "event_type": ZulipEventType.UPDATE_MESSAGE,
                "message": edited_message_mock
            }) == {}

    class TestDeleteFromConversation:
        """Tests for delete_from_conversation method"""

        @pytest.mark.asyncio
        async def test_delete_message(self,
                                      manager,
                                      conversation_info_mock,
                                      cached_private_message_mock,
                                      standard_private_conversation_id):
            """Test deleting a message"""
            manager.conversations[standard_private_conversation_id] = conversation_info_mock
            manager.message_cache.get_message_by_id.return_value = cached_private_message_mock
            manager.message_cache.delete_message.return_value = True

            with patch.object(ThreadHandler, "remove_thread_info", return_value=(False, None)):
                await manager.delete_from_conversation(
                    outgoing_event={
                        "deleted_ids": ["12345"],
                        "conversation_id": standard_private_conversation_id
                    }
                )

                manager.message_cache.get_message_by_id.assert_called_once_with(
                    conversation_id=standard_private_conversation_id,
                    message_id="12345"
                )
                manager.message_cache.delete_message.assert_called_once_with(
                    standard_private_conversation_id, "12345"
                )

        @pytest.mark.asyncio
        async def test_delete_nonexistent_message(self,
                                                  manager,
                                                  standard_private_conversation_id):
            """Test deleting a non-existent message"""
            manager.conversations[standard_private_conversation_id] = ConversationInfo(
                platform_conversation_id="101_102",
                conversation_id=standard_private_conversation_id,
                conversation_type="private"
            )
            manager.message_cache.get_message_by_id.return_value = None

            await manager.delete_from_conversation(
                outgoing_event={
                    "message_id": "99999",
                    "conversation_id": standard_private_conversation_id
                }
            )

            manager.message_cache.delete_message.assert_not_called()

    class TestMigrateBetweenConversations:
        """Tests for migrate_between_conversations method"""

        @pytest.fixture
        def migration_message_mock(self):
            """Create a mock Zulip migration message event"""
            return {
                "type": "stream",
                "stream_id": 201,
                "orig_subject": "Old Topic",
                "subject": "New Topic",
                "message_ids": [12345, 12346]
            }

        @pytest.fixture
        def standard_old_conversation_id(self):
            """Create a standard stream conversation ID"""
            return "zulip_mnj0vhedI9CXozfAsNbc"

        @pytest.fixture
        def standard_new_conversation_id(self):
            """Create a standard stream conversation ID"""
            return "zulip_0yBWuUfWNIV3CRcV2lU6"

        @pytest.mark.asyncio
        async def test_migrate_messages(self,
                                        manager,
                                        migration_message_mock,
                                        standard_old_conversation_id,
                                        standard_new_conversation_id):
            """Test migrating messages between conversations"""
            manager.conversations[standard_old_conversation_id] = ConversationInfo(
                platform_conversation_id="201/Old Topic",
                conversation_id=standard_old_conversation_id,
                conversation_type="stream"
            )
            manager.conversations[standard_old_conversation_id].messages.add("12345")
            manager.conversations[standard_old_conversation_id].messages.add("12346")

            delta = await manager.migrate_between_conversations({
                "message": migration_message_mock,
                "server": {"realm_name": "Test Realm"}
            })

            assert delta["conversation_id"] == standard_new_conversation_id

            assert len(delta["deleted_message_ids"]) == 2
            assert manager.message_cache.migrate_message.call_count == 2

        @pytest.mark.asyncio
        async def test_migrate_nonexistent_conversation(self,
                                                        manager,
                                                        migration_message_mock,
                                                        standard_new_conversation_id):
            """Test migrating from a non-existent conversation"""
            # We use the same mock, but do not setup conversation before calling the method
            # also, "201/Nonexistent" is converted to "zulip_ozS8axkVdp7Q9bPtvmxL"
            delta = await manager.migrate_between_conversations({
                "message": migration_message_mock,
                "server": None
            })

            assert delta["conversation_id"] == standard_new_conversation_id
            assert "zulip_ozS8axkVdp7Q9bPtvmxL" not in manager.conversations
            assert manager.message_cache.migrate_message.call_count == 0

    class TestHelperMethods:
        """Tests for helper methods"""

        @pytest.fixture
        def message_builder_mock(self, standard_private_conversation_id):
            """Create a mock MessageBuilder"""
            message_builder = MagicMock()
            message_builder.reset.return_value = message_builder
            message_builder.with_basic_info.return_value = message_builder
            message_builder.with_sender_info.return_value = message_builder
            message_builder.with_content.return_value = message_builder
            message_builder.with_thread_info.return_value = message_builder
            message_builder.build.return_value = {
                "message_id": "12345",
                "conversation_id": standard_private_conversation_id,
                "text": "Hello, world!",
                "sender_id": "101",
                "sender_name": "Test User"
            }
            return message_builder

        @pytest.mark.asyncio
        async def test_create_message(self,
                                      manager,
                                      user_info_mock,
                                      conversation_info_mock,
                                      private_message_mock,
                                      cached_private_message_mock,
                                      message_builder_mock,
                                      standard_private_conversation_id):
            """Test creating a message"""
            thread_info = None
            manager.message_builder = message_builder_mock
            manager.message_cache.add_message.return_value = cached_private_message_mock

            result = await manager._create_message(
                private_message_mock,
                conversation_info_mock,
                user_info_mock,
                thread_info
            )

            assert result.message_id == "12346"
            assert result.conversation_id == standard_private_conversation_id
            assert result.text == "Hello!"
