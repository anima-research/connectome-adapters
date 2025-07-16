import asyncio
import os
import pytest
from datetime import datetime

from unittest.mock import AsyncMock, MagicMock, patch

from src.adapters.slack_adapter.conversation.data_classes import ConversationInfo
from src.adapters.slack_adapter.conversation.manager import Manager, SlackEventType
from src.adapters.slack_adapter.conversation.thread_handler import ThreadHandler
from src.adapters.slack_adapter.conversation.reaction_handler import ReactionHandler

from src.core.cache.message_cache import MessageCache, CachedMessage
from src.core.cache.attachment_cache import AttachmentCache
from src.core.cache.user_cache import UserInfo

class TestManager:
    """Tests for the Slack conversation manager class"""

    @pytest.fixture
    def manager(self, slack_config, cache_mock):
        """Create a Manager with mocked dependencies"""
        manager = Manager(slack_config)
        manager.cache = cache_mock
        return manager

    @pytest.fixture
    def user_info_mock(self):
        """Create a mock UserInfo"""
        return UserInfo(
            user_id="U12345678",
            username="Slack User",
            is_bot=False
        )

    @pytest.fixture
    def standard_conversation_id(self):
        """Create a mock standard conversation ID"""
        return "slack_F0OIohoDYwVnEyYccO7j"

    @pytest.fixture
    def conversation_info_mock(self, standard_conversation_id):
        """Create a mock ConversationInfo"""
        return ConversationInfo(
            platform_conversation_id="T123/C456",
            conversation_id=standard_conversation_id,
            conversation_type="channel",
            conversation_name=None,
            messages=set(["1625176800.123456"])
        )

    @pytest.fixture
    def cached_message_mock(self, standard_conversation_id):
        """Create a mock cached message"""
        return CachedMessage(
            message_id="1625176800.123456",
            conversation_id=standard_conversation_id,
            thread_id=None,
            sender_id="U12345678",
            sender_name="Slack User",
            text="Hello world!",
            timestamp=1625176800123,  # 2021-07-01 in ms
            edit_timestamp=None,
            edited=False,
            is_from_bot=False,
            reactions={"+1": 1},
            is_pinned=False
        )

    @pytest.fixture
    def mock_slack_message(self):
        """Create a mock Slack message"""
        return {
            "type": "message",
            "ts": "1625176800.123456",
            "text": "Hello world!",
            "user": "U12345678",
            "team": "T123",
            "channel": "C456",
            "channel_type": "channel",
            "event_ts": "1625176800.123456",
            "thread_ts": "1625176800.001456",
            "blocks": []
        }

    @pytest.fixture
    def mock_slack_edited_message(self):
        """Create a mock Slack edited message event"""
        return {
            "type": "message",
            "subtype": "message_changed",
            "message": {
                "type": "message",
                "text": "Hello world! (edited)",
                "user": "U12345678",
                "team": "T123",
                "edited": {
                    "user": "U12345678",
                    "ts": "1625176900.000000"
                },
                "ts": "1625176800.123456"
            },
            "previous_message": {
                "type": "message",
                "text": "Hello world!",
                "user": "U12345678",
                "ts": "1625176800.123456"
            },
            "channel": "C456",
            "ts": "1625176900.000001",
            "event_ts": "1625176900.000001",
            "team": "T123"
        }

    @pytest.fixture
    def mock_slack_deleted_message(self):
        """Create a mock Slack deleted message event"""
        return {
            "type": "message",
            "subtype": "message_deleted",
            "previous_message": {
                "type": "message",
                "text": "Hello world!",
                "user": "U12345678",
                "ts": "1625176800.123456"
            },
            "channel": "C456",
            "ts": "1625177000.000000",
            "deleted_ts": "1625176800.123456",
            "event_ts": "1625177000.000000",
            "team": "T123"
        }

    @pytest.fixture
    def mock_slack_reaction_event(self):
        """Create a mock Slack reaction event"""
        return {
            "event_type": SlackEventType.REACTION,
            "message": {
                "type": "reaction_added",
                "user": "U12345678",
                "reaction": "fire",
                "item": {
                    "type": "message",
                    "channel": "C456",
                    "ts": "1625176800.123456"
                },
                "team": "T123"
            },
            "updated_content": "",
            "user_id": None,
            "mentions": []
        }

    @pytest.fixture
    def mock_slack_pin_event(self):
        """Create a mock Slack pin event"""
        return {
            "event_type": SlackEventType.PIN,
            "message": {
                "type": "pin_added",
                "user": "U12345678",
                "item": {
                    "ts": "1625176800.123456",
                    "message": {
                        "text": "Hello world!",
                        "user": "U12345678",
                        "ts": "1625176800.123456"
                    }
                },
                "channel": "C456",
                "event_ts": "1625177200.000000",
                "ts": "1625177200.000000",
                "team": "T123"
            },
            "updated_content": "",
            "user_id": None,
            "mentions": []
        }

    @pytest.fixture
    def mock_slack_unpin_event(self):
        """Create a mock Slack unpin event"""
        return {
            "event_type": SlackEventType.PIN,
            "message": {
                "type": "pin_removed",
                "user": "U12345678",
                "item": {
                    "type": "message",
                    "channel": "C456",
                    "ts": "1625176800.123456",
                    "message": {
                        "type": "message",
                        "text": "Hello world!",
                        "user": "U12345678",
                        "ts": "1625176800.123456"
                    }
                },
                "channel": "C456",
                "event_ts": "1625177300.000000",
                "ts": "1625177300.000000",
                "team": "T123"
            },
            "updated_content": "",
            "user_id": None,
            "mentions": []
        }

    @pytest.fixture
    def attachment_mock(self):
        """Create a mock attachment"""
        return {
            "attachment_id": "F12345678",
            "filename": "F12345678.txt",
            "size": 12345,
            "content_type": "text/plain",
            "content": "dGVzdAo=",
            "url": "https://slack.com/files/F12345678",
            "processable": True
        }

    class TestGetOrCreateConversation:
        """Tests for conversation creation and identification"""

        @pytest.mark.asyncio
        async def test_get_platform_conversation_id(self, manager, mock_slack_message):
            """Test getting conversation ID from a message"""
            assert await manager._get_platform_conversation_id(mock_slack_message) == "T123/C456"

        @pytest.mark.asyncio
        async def test_get_platform_conversation_id_from_item(self, manager):
            """Test getting conversation ID from an item object"""
            assert await manager._get_platform_conversation_id({
                "team": "T123",
                "item": {"channel": "C456"}
            }) == "T123/C456"

        @pytest.mark.asyncio
        async def test_get_conversation_type(self, manager, mock_slack_message):
            """Test getting conversation type from a message"""
            assert await manager._get_conversation_type(mock_slack_message) == "channel"

        @pytest.mark.asyncio
        async def test_get_or_create_conversation_info_new(self,
                                                           manager,
                                                           mock_slack_message,
                                                           standard_conversation_id):
            """Test creating a new conversation"""
            assert len(manager.conversations) == 0
            conversation_info = await manager._get_or_create_conversation_info(
                {"message": mock_slack_message}
            )

            assert len(manager.conversations) == 1
            assert conversation_info.platform_conversation_id == "T123/C456"
            assert conversation_info.conversation_id == standard_conversation_id
            assert conversation_info.conversation_type == "channel"
            assert conversation_info.just_started is True

        @pytest.mark.asyncio
        async def test_get_or_create_conversation_info_existing(self,
                                                                manager,
                                                                mock_slack_message,
                                                                standard_conversation_id):
            """Test getting an existing conversation"""
            manager.conversations[standard_conversation_id] = ConversationInfo(
                platform_conversation_id="T123/C456",
                conversation_id=standard_conversation_id,
                conversation_type="channel"
            )
            conversation_info = await manager._get_or_create_conversation_info(
                {"message": mock_slack_message}
            )

            assert len(manager.conversations) == 1
            assert conversation_info.conversation_id == standard_conversation_id
            assert conversation_info.conversation_type == "channel"

    class TestAddToConversation:
        """Tests for add_to_conversation method"""

        @pytest.mark.asyncio
        async def test_add_message(self,
                                   manager,
                                   mock_slack_message,
                                   cached_message_mock,
                                   attachment_mock,
                                   standard_conversation_id):
            """Test adding a message with attachment"""
            with patch.object(manager, "_create_message", return_value=cached_message_mock), \
                 patch.object(manager, "_update_attachment", return_value=[attachment_mock]):

                delta = await manager.add_to_conversation({
                    "message": mock_slack_message,
                    "attachments": [attachment_mock],
                    "user": {"id": "U12345678", "name": "Slack User"}
                })

                assert delta["conversation_id"] == standard_conversation_id
                assert delta["fetch_history"] is True  # New conversation should fetch history

                assert len(delta["added_messages"]) == 1
                assert delta["added_messages"][0]["message_id"] == "1625176800.123456"
                assert delta["added_messages"][0]["attachments"] == [attachment_mock]

        @pytest.mark.asyncio
        async def test_add_empty_message(self, manager):
            """Test adding an empty message"""
            assert not await manager.add_to_conversation({})

    class TestUpdateConversation:
        """Tests for update_conversation method"""

        @pytest.mark.asyncio
        async def test_update_nonexistent_conversation(self, manager, mock_slack_edited_message):
            """Test updating a non-existent conversation"""
            assert not await manager.update_conversation({
                "event_type": SlackEventType.EDITED_MESSAGE,
                "message": mock_slack_edited_message
            })

        @pytest.mark.asyncio
        async def test_update_message_content(self,
                                              manager,
                                              conversation_info_mock,
                                              cached_message_mock,
                                              mock_slack_edited_message,
                                              standard_conversation_id):
            """Test updating a message's content"""
            with patch.object(manager.cache.message_cache, "get_message_by_id", return_value=cached_message_mock):
                manager.conversations[standard_conversation_id] = conversation_info_mock

                delta = await manager.update_conversation({
                    "event_type": SlackEventType.EDITED_MESSAGE,
                    "message": mock_slack_edited_message,
                    "updated_content": "",
                    "user_id": None,
                    "mentions": []
                })

                assert delta["conversation_id"] == standard_conversation_id
                assert len(delta["updated_messages"]) == 1
                assert delta["updated_messages"][0]["message_id"] == "1625176800.123456"
                assert cached_message_mock.text == mock_slack_edited_message["message"]["text"]

        @pytest.mark.asyncio
        async def test_update_message_reaction(self,
                                               manager,
                                               conversation_info_mock,
                                               cached_message_mock,
                                               mock_slack_reaction_event,
                                               standard_conversation_id):
            """Test updating a message's reactions"""
            with patch.object(manager.cache.message_cache, "get_message_by_id", return_value=cached_message_mock):
                manager.conversations[standard_conversation_id] = conversation_info_mock

                with patch.object(ReactionHandler, "update_message_reactions") as mock_update_reactions:
                    delta = await manager.update_conversation(mock_slack_reaction_event)

                    assert delta["conversation_id"] == standard_conversation_id
                    mock_update_reactions.assert_called_once()

        @pytest.mark.asyncio
        async def test_pin_message(self,
                                   manager,
                                   cached_message_mock,
                                   conversation_info_mock,
                                   mock_slack_pin_event,
                                   standard_conversation_id):
            """Test pinning a message"""
            with patch.object(manager.cache.message_cache, "get_message_by_id", return_value=cached_message_mock):
                manager.conversations[standard_conversation_id] = conversation_info_mock

                delta = await manager.update_conversation(mock_slack_pin_event)

                assert delta["conversation_id"] == standard_conversation_id
                assert cached_message_mock.is_pinned is True
                assert cached_message_mock.message_id in conversation_info_mock.pinned_messages
                assert len(delta["pinned_message_ids"]) == 1
                assert delta["pinned_message_ids"][0] == cached_message_mock.message_id

        @pytest.mark.asyncio
        async def test_unpin_message(self,
                                     manager,
                                     cached_message_mock,
                                     conversation_info_mock,
                                     mock_slack_unpin_event,
                                     standard_conversation_id):
            """Test unpinning a message"""
            cached_message_mock.is_pinned = True
            conversation_info_mock.pinned_messages.add(cached_message_mock.message_id)

            with patch.object(manager.cache.message_cache, "get_message_by_id", return_value=cached_message_mock):
                manager.conversations[standard_conversation_id] = conversation_info_mock

                delta = await manager.update_conversation(mock_slack_unpin_event)

                assert delta["conversation_id"] == standard_conversation_id
                assert cached_message_mock.is_pinned is False
                assert cached_message_mock.message_id not in conversation_info_mock.pinned_messages
                assert len(delta["unpinned_message_ids"]) == 1
                assert delta["unpinned_message_ids"][0] == cached_message_mock.message_id

    class TestDeleteFromConversation:
        """Tests for delete_from_conversation method"""

        @pytest.mark.asyncio
        async def test_get_deleted_message_ids(self, manager, mock_slack_deleted_message):
            """Test getting deleted message IDs from an event"""
            message_ids = await manager._get_deleted_message_ids(mock_slack_deleted_message)
            assert len(message_ids) == 1
            assert message_ids[0] == "1625176800.123456"

        @pytest.mark.asyncio
        async def test_get_deleted_message_ids_empty(self, manager):
            """Test getting deleted message IDs from an event with no previous message"""
            assert len(await manager._get_deleted_message_ids({})) == 0

        @pytest.mark.asyncio
        async def test_delete_message(self,
                                      manager,
                                      conversation_info_mock,
                                      cached_message_mock,
                                      mock_slack_deleted_message,
                                      standard_conversation_id):
            """Test deleting a message"""
            manager.conversations[standard_conversation_id] = conversation_info_mock

            with patch.object(manager.cache.message_cache, "get_message_by_id", return_value=cached_message_mock):
                with patch.object(manager.cache.message_cache, "delete_message", return_value=True):
                    with patch.object(ThreadHandler, "remove_thread_info"):
                        delta = await manager.delete_from_conversation(
                            incoming_event=mock_slack_deleted_message
                        )

                        assert delta["conversation_id"] == standard_conversation_id
                        assert "1625176800.123456" in delta["deleted_message_ids"]

    class TestAttachmentHandling:
        """Tests for attachment handling"""

        @pytest.mark.asyncio
        async def test_update_attachment(self, manager, attachment_mock, standard_conversation_id):
            """Test updating attachment info in conversation info"""
            attachment_mock["attachment_type"] = "document"
            attachment_mock["created_at"] = datetime.now()

            conversation_info = ConversationInfo(
                platform_conversation_id="T123/C456",
                conversation_id=standard_conversation_id,
                conversation_type="channel"
            )

            cached_attachment = MagicMock()
            cached_attachment.attachment_id = "F12345678"

            with patch.object(manager.cache.attachment_cache, "add_attachment", return_value=cached_attachment):
                result = await manager._update_attachment(
                    conversation_info, [attachment_mock]
                )

                assert len(result) == 1
                assert result[0]["attachment_id"] == attachment_mock["attachment_id"]
                assert result[0]["filename"] == attachment_mock["filename"]
                assert result[0]["size"] == attachment_mock["size"]
                assert result[0]["content_type"] == attachment_mock["content_type"]
                assert result[0]["url"] == attachment_mock["url"]
                assert "attachment_type" not in result[0]
                assert "created_at" not in result[0]
                assert "F12345678" in conversation_info.attachments
