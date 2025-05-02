import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from adapters.telegram_adapter.adapter.conversation.manager import Manager
from adapters.telegram_adapter.adapter.conversation.data_classes import ConversationInfo

from core.cache.attachment_cache import AttachmentCache
from core.cache.message_cache import CachedMessage, MessageCache
from core.conversation.base_data_classes import UserInfo

class TestConversationManager:
    """Tests for ConversationManager class"""

    # --- COMMON MOCK FIXTURES ---

    @pytest.fixture
    def mock_peer_id_with_user_id(self):
        """Create a mock peer id with user id"""
        class MockUserId:
            def __init__(self):
                self.user_id = "456"

        return MockUserId()

    @pytest.fixture
    def mock_peer_id_with_chat_id(self):
        """Create a mock peer id with chat id"""
        class MockChatId:
            def __init__(self):
                self.chat_id = "101112"

        return MockChatId()

    @pytest.fixture
    def mock_reply_to_message(self):
        """Create a mock reply to message"""
        class MockReplyTo:
            def __init__(self):
                self.reply_to_msg_id = "123"

        return MockReplyTo()

    @pytest.fixture
    def mock_message_base(self):
        """Base for creating mock messages"""
        def _create_message(id, peer_id, message_text, reply_to=None, reactions=None):
            message = MagicMock()
            message.id = id
            message.peer_id = peer_id
            message.date = datetime.now()
            message.message = message_text
            message.reactions = reactions
            message.reply_to = reply_to
            return message
        return _create_message

    @pytest.fixture
    def mock_telethon_message(self,
                              mock_message_base,
                              mock_peer_id_with_user_id):
        """Create a mock Telethon message"""
        return mock_message_base("123", mock_peer_id_with_user_id, "Test message")

    @pytest.fixture
    def mock_telethon_user(self):
        """Create a mock Telethon user"""
        user = MagicMock()
        user.id = "456"
        user.username = "testuser"
        user.first_name = "Test"
        user.last_name = "User"
        user.bot = False
        return user

    @pytest.fixture
    def mock_message_cache(self):
        """Create a mocked MessageCache"""
        cache = MagicMock()
        cache.add_message = AsyncMock()
        cache.get_message_by_id = AsyncMock(return_value=None)
        cache.delete_message = AsyncMock(return_value=True)
        cache.migrate_messages = AsyncMock()
        cache.messages = {}
        cache.maintenance_task = None
        return cache

    @pytest.fixture
    def mock_attachment_cache(self):
        """Create a mocked AttachmentCache"""
        cache = MagicMock()
        cache.attachments = {}
        cache.maintenance_task = None
        return cache

    @pytest.fixture
    def manager(self, patch_config, mock_message_cache, mock_attachment_cache):
        """Create a ConversationManager with mocked dependencies"""
        with patch.object(MessageCache, "__new__", return_value=mock_message_cache):
            with patch.object(AttachmentCache, "__new__", return_value=mock_attachment_cache):
                return Manager(patch_config)

    @pytest.fixture
    def cached_message_factory(self):
        """Factory for creating cached messages with default values"""
        def _create_cached_message(message_id="123",
                                   conversation_id="456",
                                   thread_id=None,
                                   text="Test message",
                                   reactions=None):
            return CachedMessage(
                message_id=message_id,
                conversation_id=conversation_id,
                thread_id=thread_id,
                sender_id="456",
                sender_name="Test User",
                text=text,
                timestamp=datetime.now(),
                is_from_bot=False,
                reactions=reactions or {}
            )
        return _create_cached_message

    # --- TEST CLASSES ---

    class TestConversationCreateUpdate:
        """Tests for conversation creation and update"""

        @pytest.fixture
        def mock_telethon_group_message(self,
                                        mock_message_base,
                                        mock_peer_id_with_chat_id):
            """Create a mock Telethon message from a group"""
            return mock_message_base("789", mock_peer_id_with_chat_id, "Group message")

        @pytest.mark.asyncio
        async def test_create_private_conversation(self,
                                                   manager,
                                                   mock_telethon_message,
                                                   mock_telethon_user):
            """Test creating a new private conversation"""
            with patch.object(manager.message_builder, "build") as mock_build:
                mock_build.return_value = {
                    "message_id": "123",
                    "conversation_id": "456",
                    "text": "Test message",
                    "timestamp": datetime.now(),
                    "sender_id": "789",
                    "sender_name": "Test User"
                }

                cached_msg_mock = MagicMock()
                cached_msg_mock.text = "Test message"
                manager.message_cache.add_message.return_value = cached_msg_mock

                delta = await manager.add_to_conversation({
                    "message": mock_telethon_message,
                    "user": mock_telethon_user
                })

            assert delta["fetch_history"] is True
            assert delta["conversation_id"] == "456"

            assert "456" in manager.conversations
            assert manager.conversations["456"].conversation_type == "private"

            assert "456" in manager.conversations["456"].known_members
            assert manager.conversations["456"].known_members["456"].username == "testuser"

            manager.message_cache.add_message.assert_called_once()

        @pytest.mark.asyncio
        async def test_create_group_conversation(self,
                                                 manager,
                                                 mock_telethon_group_message,
                                                 mock_telethon_user):
            """Test creating a new group conversation"""
            delta = await manager.add_to_conversation({
                "message": mock_telethon_group_message,
                "user": mock_telethon_user
            })

            assert delta["fetch_history"] is True
            assert delta["conversation_id"] == "-101112"

            assert "-101112" in manager.conversations
            assert manager.conversations["-101112"].conversation_type == "group"

        @pytest.mark.asyncio
        async def test_update_existing_conversation(self,
                                                    manager,
                                                    mock_telethon_message,
                                                    mock_telethon_user,
                                                    mock_message_base,
                                                    mock_peer_id_with_user_id):
            """Test updating an existing conversation"""
            await manager.add_to_conversation({
                "message": mock_telethon_message,
                "user": mock_telethon_user
            })

            manager.message_cache.add_message.reset_mock()
            delta = await manager.add_to_conversation({
                "message": mock_message_base("124", mock_peer_id_with_user_id, "Second message"),
                "user": mock_telethon_user
            })

            assert delta["fetch_history"] is False
            assert delta["conversation_id"] == "456"

    class TestThreadHandling:
        """Tests for thread/reply handling"""

        @pytest.fixture
        def mock_telethon_reply_message(self,
                                        mock_message_base,
                                        mock_peer_id_with_user_id,
                                        mock_reply_to_message):
            """Create a mock Telethon message that is a reply"""
            return mock_message_base(
                "456", mock_peer_id_with_user_id, "Reply message", mock_reply_to_message
            )

        @pytest.mark.asyncio
        async def test_handle_reply(self,
                                    manager,
                                    mock_telethon_message,
                                    mock_telethon_reply_message,
                                    mock_telethon_user):
            """Test handling a reply to create a thread"""
            await manager.add_to_conversation({
                "message": mock_telethon_message,
                "user": mock_telethon_user
            })
            await manager.add_to_conversation({
                "message": mock_telethon_reply_message,
                "user": mock_telethon_user
            })

            conversation = manager.conversations["456"]
            assert "123" in conversation.threads
            assert conversation.threads["123"].thread_id == "123"

    class TestMessageHandling:
        """Tests for message handling"""

        @pytest.fixture
        def mock_telethon_edited_message(self,
                                        mock_message_base,
                                        mock_peer_id_with_user_id):
            """Create a mock Telethon edited message"""
            return mock_message_base(
                "123", mock_peer_id_with_user_id, "Edited message"
            )

        @pytest.fixture
        def mock_pin_message(self,
                            mock_message_base,
                            mock_peer_id_with_user_id,
                            mock_reply_to_message):
            """Create a mock pin message event"""
            return mock_message_base(
                "789", mock_peer_id_with_user_id, "", mock_reply_to_message
            )

        @pytest.fixture
        def mock_unpin_message(self, mock_peer_id_with_user_id):
            """Create a mock unpin message event"""
            message = MagicMock()
            message.messages = ["123"]  # ID of the message being unpinned
            message.peer_id = None
            message.peer = mock_peer_id_with_user_id
            return message

        @pytest.fixture
        def mock_delete_message(self):
            """Create a mock delete message event"""
            message = MagicMock()
            message.deleted_ids = [123]
            message.user_id = None
            message.chat_id = None
            message.channel_id = None
            return message

        @pytest.mark.asyncio
        async def test_edit_message(self,
                                    manager,
                                    mock_telethon_message,
                                    mock_telethon_edited_message,
                                    mock_telethon_user,
                                    cached_message_factory):
            """Test editing a message"""
            await manager.add_to_conversation({
                "message": mock_telethon_message,
                "user": mock_telethon_user
            })

            cached_msg = cached_message_factory(text="Test message")
            manager.message_cache.get_message_by_id.return_value = cached_msg
            delta = await manager.update_conversation({
                "event_type": "edited_message",
                "message": mock_telethon_edited_message
            })

            assert len(delta["updated_messages"]) == 1
            assert delta["updated_messages"][0]["text"] == "Edited message"
            assert cached_msg.text == "Edited message"

            manager.message_cache.get_message_by_id.return_value = None

        @pytest.mark.asyncio
        async def test_delete_message(self,
                                      manager,
                                      mock_telethon_message,
                                      mock_telethon_user,
                                      cached_message_factory,
                                      mock_delete_message):
            """Test deleting a message"""
            await manager.add_to_conversation({
                "message": mock_telethon_message,
                "user": mock_telethon_user
            })
            cached_msg = cached_message_factory(text="Test message")
            manager.message_cache.get_message_by_id.return_value = cached_msg
            manager.message_cache.messages = { "456": {"123": cached_msg} }


            result = await manager.delete_from_conversation(incoming_event={"event": mock_delete_message})
            assert result["conversation_id"] == "456"
            assert result["deleted_message_ids"] == ["123"]

            manager.message_cache.delete_message.assert_called_once_with("456", "123")
            manager.message_cache.messages = {}

        @pytest.mark.asyncio
        async def test_pin_message(self,
                                   manager,
                                   mock_telethon_message,
                                   mock_telethon_user,
                                   mock_pin_message,
                                   cached_message_factory):
            """Test pinning a message"""
            await manager.add_to_conversation({
                "message": mock_telethon_message,
                "user": mock_telethon_user
            })

            cached_msg = cached_message_factory(message_id="123", conversation_id="456")
            manager.message_cache.get_message_by_id.return_value = cached_msg
            delta = await manager.update_conversation({
                "event_type": "pinned_message",
                "message": mock_pin_message
            })

            assert delta["conversation_id"] == "456"
            assert delta["pinned_message_ids"] == ["123"]
            assert cached_msg.is_pinned is True
            assert "123" in manager.conversations["456"].pinned_messages

        @pytest.mark.asyncio
        async def test_pin_message_not_found(self,
                                            manager,
                                            mock_telethon_message,
                                            mock_telethon_user,
                                            mock_pin_message):
            """Test pinning a message that doesn't exist in the cache"""
            await manager.add_to_conversation({
                "message": mock_telethon_message,
                "user": mock_telethon_user
            })
            manager.message_cache.get_message_by_id.return_value = None
            delta = await manager.update_conversation({
                "event_type": "pinned_message",
                "message": mock_pin_message
            })

            assert "pinned_message_ids" not in delta
            assert delta["conversation_id"] == "456"  # Conversation is created anyway

        @pytest.mark.asyncio
        async def test_unpin_message(self,
                                     manager,
                                     mock_telethon_message,
                                     mock_telethon_user,
                                     mock_unpin_message,
                                     cached_message_factory):
            """Test unpinning a message"""
            await manager.add_to_conversation({
                "message": mock_telethon_message,
                "user": mock_telethon_user
            })

            cached_msg = cached_message_factory(message_id="123", conversation_id="456")
            cached_msg.is_pinned = True
            manager.message_cache.get_message_by_id.return_value = cached_msg
            manager.conversations["456"].pinned_messages.add("123")
            delta = await manager.update_conversation({
                "event_type": "unpinned_message",
                "message": mock_unpin_message
            })

            assert delta["conversation_id"] == "456"
            assert delta["unpinned_message_ids"] == ["123"]
            assert cached_msg.is_pinned is False
            assert "123" not in manager.conversations["456"].pinned_messages

    class TestReactionHandling:
        """Tests for message reactions"""

        @pytest.fixture
        def create_reactions_mock(self):
            """Factory for creating reaction mocks"""
            def _create_reactions(reactions_data):
                """Create a mock reactions object
                Args:
                    reactions_data: List of tuples with (emoji, count)
                """
                reactions = MagicMock()
                reactions.results = []

                for emoji, count in reactions_data:
                    reaction = MagicMock()
                    reaction.reaction = MagicMock()
                    reaction.reaction.emoticon = emoji
                    reaction.count = count
                    reactions.results.append(reaction)

                return reactions
            return _create_reactions

        @pytest.fixture
        def mock_telethon_reaction_message(self,
                                        mock_message_base,
                                        mock_peer_id_with_user_id,
                                        create_reactions_mock):
            """Create a mock Telethon message with reactions"""
            reactions = create_reactions_mock([("👍", 2), ("❤️", 1)])
            return mock_message_base(
                "123",
                mock_peer_id_with_user_id,
                "Message with reactions",
                reactions=reactions
            )

        @pytest.mark.asyncio
        async def test_add_reactions(self,
                                    manager,
                                    mock_telethon_message,
                                    mock_telethon_reaction_message,
                                    mock_telethon_user,
                                    cached_message_factory):
            """Test adding reactions to a message"""
            await manager.add_to_conversation({
                "message": mock_telethon_message,
                "user": mock_telethon_user
            })

            cached_msg = cached_message_factory(
                text=mock_telethon_reaction_message.message,
                reactions={}
            )
            manager.message_cache.get_message_by_id.return_value = cached_msg
            delta = await manager.update_conversation({
                "event_type": "edited_message",
                "message": mock_telethon_reaction_message
            })

            assert "added_reactions" in delta
            assert "thumbs_up" in delta["added_reactions"]
            assert "red_heart" in delta["added_reactions"]

            manager.message_cache.get_message_by_id.return_value = None

        @pytest.mark.asyncio
        async def test_remove_reactions(self,
                                       manager,
                                       mock_telethon_message,
                                       mock_telethon_user,
                                       mock_message_base,
                                       mock_peer_id_with_user_id,
                                       create_reactions_mock,
                                       cached_message_factory):
            """Test removing reactions from a message"""
            await manager.add_to_conversation({
                "message": mock_telethon_message,
                "user": mock_telethon_user
            })

            cached_msg = cached_message_factory(reactions={"thumbs_up": 2, "red_heart": 1})
            manager.message_cache.get_message_by_id.return_value = cached_msg
            reactions = create_reactions_mock([("👍", 1)])  # Only 👍 with reduced count
            edited_msg = mock_message_base(
                "123",
                mock_peer_id_with_user_id,
                cached_msg.text,
                reactions=reactions
            )
            delta = await manager.update_conversation({
                "event_type": "edited_message",
                "message": edited_msg
            })

            assert "removed_reactions" in delta
            assert "thumbs_up" in delta["removed_reactions"]  # Count decreased
            assert "red_heart" in delta["removed_reactions"]  # Completely removed

            manager.message_cache.get_message_by_id.return_value = None
