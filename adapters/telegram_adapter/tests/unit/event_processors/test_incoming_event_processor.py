import json
import pytest

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from adapters.telegram_adapter.adapter.attachment_loaders.downloader import Downloader
from adapters.telegram_adapter.adapter.event_processors.incoming_event_processor import (
    IncomingEventProcessor, TelegramIncomingEventType
)

class TestIncomingEventProcessor:
    """Tests for the IncomingEventProcessor class"""

    @pytest.fixture
    def telethon_client_mock(self):
        """Create a mocked Telethon client"""
        client = AsyncMock()
        client.get_entity = AsyncMock()
        return client

    @pytest.fixture
    def conversation_manager_mock(self):
        """Create a mocked conversation manager"""
        manager = AsyncMock()
        manager.add_to_conversation = AsyncMock()
        manager.update_conversation = AsyncMock()
        manager.delete_from_conversation = AsyncMock()
        manager.migrate_conversation = AsyncMock()
        manager.attachment_download_required = MagicMock(return_value=False)
        return manager

    @pytest.fixture
    def downloader_mock(self):
        """Create a mocked downloader"""
        downloader = AsyncMock()
        downloader.download_attachment = AsyncMock(return_value={})
        return downloader

    @pytest.fixture
    def processor(self, patch_config, telethon_client_mock, conversation_manager_mock):
        """Create a TelegramEventsProcessor with mocked dependencies"""
        with patch.object(Downloader, "__new__") as DownloaderMock:
            DownloaderMock.return_value = AsyncMock()
            DownloaderMock.return_value.download_attachment = AsyncMock(return_value={})
            processor = IncomingEventProcessor(patch_config, telethon_client_mock, conversation_manager_mock)
            processor.incoming_event_builder = MagicMock()
            return processor

    @pytest.fixture
    def message_event_mock(self):
        """Create a mock for a new message event"""
        event = MagicMock()
        message = MagicMock()
        message.id = 123
        message.text = "Text message"
        message.date = datetime.now()
        peer_id = MagicMock()
        peer_id.user_id = 456
        message.peer_id = peer_id
        event.message = message
        return event

    @pytest.fixture
    def user_mock(self):
        """Create a mock user object"""
        user = MagicMock()
        user.id = 456
        user.username = "testuser"
        user.first_name = "Test"
        user.last_name = "User"
        return user

    class TestProcessEvent:
        """Tests for the process_event method"""

        @pytest.mark.asyncio
        @pytest.mark.parametrize("event_type", [
            TelegramIncomingEventType.NEW_MESSAGE,
            TelegramIncomingEventType.EDITED_MESSAGE,
            TelegramIncomingEventType.DELETED_MESSAGE,
            TelegramIncomingEventType.CHAT_ACTION
        ])
        async def test_process_event_calls_correct_handler(self, processor, event_type):
            """Test that process_event calls the correct handler method"""
            data = {"test": "data"}
            handler_mocks = {}

            for handler_type in TelegramIncomingEventType:
                method_name = f"_handle_{handler_type.value}"
                handler_mock = AsyncMock(return_value=["event_info"])
                handler_mocks[handler_type] = handler_mock
                setattr(processor, method_name, handler_mock)

            event = {"type": event_type, "data": data}
            assert await processor.process_event(event) == ["event_info"]
            handler_mocks[event_type].assert_called_once_with(event)

        @pytest.mark.asyncio
        async def test_process_unknown_event(self, processor):
            """Test processing an unknown event type"""
            result = await processor.process_event({"type": "unknown_event", "data": MagicMock()})
            assert result == []

        @pytest.mark.asyncio
        async def test_process_event_exception(self, processor, message_event_mock):
            """Test handling exceptions during event processing"""
            with patch.object(processor, "_handle_new_message", side_effect=Exception("Test error")):
                result = await processor.process_event({"type": "new_message", "data": message_event_mock})
                assert result == []

    class TestHandleNewMessage:
        """Tests for the _handle_new_message method"""

        @pytest.mark.asyncio
        async def test_handle_new_message(self, processor, message_event_mock, user_mock):
            """Test handling a new message with an attachment"""
            attachment_info = {
                "attachment_type": "photo",
                "attachment_id": "photo123",
                "file_extension": "jpg",
                "file_path": "/path/to/photo.jpg"
            }

            processor.downloader.download_attachment.return_value = attachment_info
            processor.conversation_manager.attachment_download_required.return_value = True

            added_message = {
                "message_id": "123",
                "conversation_id": "456",
                "text": "Text message",
                "sender": {"user_id": "456", "display_name": "Test User"},
                "timestamp": 1234567890000,
                "thread_id": None,
                "attachments": [attachment_info]
            }
            delta = {
                "conversation_id": "456",
                "fetch_history": True,
                "added_messages": [added_message]
            }

            processor.conversation_manager.add_to_conversation.return_value = delta
            processor._get_user = AsyncMock(return_value=user_mock)
            processor._fetch_conversation_history = AsyncMock(return_value=[{"some": "history"}])
            processor.incoming_event_builder.conversation_started = MagicMock(
                return_value={"event_type": "conversation_started"}
            )
            processor.incoming_event_builder.message_received = MagicMock(
                return_value={"event_type": "message_received"}
            )

            result = await processor._handle_new_message({"event": message_event_mock})

            assert len(result) == 2
            assert {"event_type": "conversation_started"} in result
            assert {"event_type": "message_received"} in result

            processor.downloader.download_attachment.assert_called_once_with(
                message_event_mock.message, True
            )
            processor.conversation_manager.add_to_conversation.assert_called_once()

            history = processor._fetch_conversation_history.return_value

            processor.incoming_event_builder.conversation_started.assert_called_once_with(delta, history)
            processor.incoming_event_builder.message_received.assert_called_once()

        @pytest.mark.asyncio
        async def test_handle_new_message_no_delta(self, processor, message_event_mock):
            """Test handling a new message with no conversation delta"""
            processor.conversation_manager.add_to_conversation.return_value = {}

            assert await processor._handle_new_message({"event": message_event_mock}) == []

        @pytest.mark.asyncio
        async def test_handle_new_message_exception(self, processor, message_event_mock):
            """Test handling exceptions during new message processing"""
            processor.conversation_manager.add_to_conversation.side_effect = Exception("Test error")

            assert await processor._handle_new_message({"event": message_event_mock}) == []

    class TestHandleEditedMessage:
        """Tests for the _handle_edited_message method"""

        @pytest.mark.asyncio
        async def test_handle_edited_message_text_change(self, processor, message_event_mock):
            """Test handling an edited message with text change"""
            updated_message = {
                "message_id": "123",
                "conversation_id": "456",
                "text": "Text message",
                "sender": {"user_id": "456", "display_name": "Test User"},
                "timestamp": 1234567890000,
                "thread_id": None,
                "attachments": []
            }
            delta = {
                "conversation_id": "456",
                "fetch_history": False,
                "updated_messages": [updated_message]
            }

            processor.conversation_manager.update_conversation.return_value = delta
            processor.incoming_event_builder.message_updated = MagicMock(
                return_value={"event_type": "message_updated"}
            )

            result = await processor._handle_edited_message({"event": message_event_mock})

            assert len(result) == 1
            assert {"event_type": "message_updated"} in result

            processor.incoming_event_builder.message_updated.assert_called_once()

        @pytest.mark.asyncio
        async def test_handle_edited_message_reaction_added(self, processor, message_event_mock):
            """Test handling an edited message with reactions added"""
            delta = {
                "conversation_id": "456",
                "message_id": "123",
                "added_reactions": ["thumbs_up", "red_heart"]
            }

            processor.conversation_manager.update_conversation.return_value = delta
            processor.incoming_event_builder.reaction_update = MagicMock(
                return_value={"event_type": "reaction_added"}
            )

            result = await processor._handle_edited_message(message_event_mock)

            assert len(result) == 2
            assert {"event_type": "reaction_added"} in result

            assert processor.incoming_event_builder.reaction_update.call_count == 2

        @pytest.mark.asyncio
        async def test_handle_edited_message_reaction_removed(self, processor, message_event_mock):
            """Test handling an edited message with reactions removed"""
            delta = {
                "conversation_id": "456",
                "message_id": "123",
                "removed_reactions": ["thumbs_up"]
            }

            processor.conversation_manager.update_conversation.return_value = delta
            processor.incoming_event_builder.reaction_update = MagicMock(
                return_value={"event_type": "reaction_removed"}
            )

            result = await processor._handle_edited_message(message_event_mock)

            assert len(result) == 1
            assert {"event_type": "reaction_removed"} in result

            processor.incoming_event_builder.reaction_update.assert_called_once_with(
                "reaction_removed", delta, "thumbs_up"
            )

    class TestHandleDeletedMessage:
        """Tests for the _handle_deleted_message method"""

        @pytest.fixture
        def deleted_message_event_mock(self):
            """Create a mock for a deleted message event"""
            event = MagicMock()
            event.deleted_ids = [123, 456]
            event.channel_id = 789
            return event

        @pytest.mark.asyncio
        async def test_handle_deleted_message_success(self, processor, deleted_message_event_mock):
            """Test handling a deleted message successfully"""
            delta = {
                "conversation_id": "789",
                "deleted_message_ids": ["123", "456"]
            }
            processor.conversation_manager.delete_from_conversation.return_value = delta
            processor.incoming_event_builder.message_deleted = MagicMock(
                return_value={"event_type": "message_deleted"}
            )

            result = await processor._handle_deleted_message({"event": deleted_message_event_mock})

            assert len(result) == 2
            assert {"event_type": "message_deleted"} in result

            processor.conversation_manager.delete_from_conversation.assert_called_once_with(
                incoming_event={"event": deleted_message_event_mock}
            )
            assert processor.incoming_event_builder.message_deleted.call_count == 2

        @pytest.mark.asyncio
        async def test_handle_deleted_message_no_conversation(self, processor, deleted_message_event_mock):
            """Test handling a deleted message with no matching conversation"""
            processor.conversation_manager.delete_from_conversation.return_value = {}

            assert await processor._handle_deleted_message(deleted_message_event_mock) == []

    class TestHandleChatAction:
        """Tests for the _handle_chat_action method"""

        @pytest.fixture
        def pin_action_event_mock(self):
            """Create a mock for a pin message chat action event"""
            reply_to = MagicMock()
            reply_to.reply_to_msg_id = 123

            peer_id = MagicMock()
            peer_id.user_id = 456

            action = MagicMock()
            action.__class__.__name__ = "MessageActionPinMessage"
            action.channel_id = 789

            message = MagicMock()
            message.reply_to = reply_to
            message.peer_id = peer_id
            message.action = action

            event = MagicMock()
            event.action_message = message
            return event

        @pytest.fixture
        def unpin_action_event_mock(self):
            """Create a mock for an unpin message event"""
            event = MagicMock()
            event.action_message = None
            original_update = MagicMock()
            original_update.messages = [123]
            peer = MagicMock()
            peer.user_id = 456
            original_update.peer = peer
            event.original_update = original_update
            return event

        @pytest.mark.asyncio
        async def test_handle_pin_message(self, processor, pin_action_event_mock):
            """Test handling a pin message chat action"""
            delta = {
                "conversation_id": "456",
                "pinned_message_ids": ["123"]
            }
            processor.conversation_manager.update_conversation.return_value = delta
            processor.incoming_event_builder.pin_status_update = MagicMock(
                return_value={"event_type": "message_pinned"}
            )

            result = await processor._handle_chat_action({"event": pin_action_event_mock})

            assert len(result) == 1
            assert {"event_type": "message_pinned"} in result

            processor.conversation_manager.update_conversation.assert_called_once_with({
                "event_type": "pinned_message",
                "message": pin_action_event_mock.action_message
            })
            processor.incoming_event_builder.pin_status_update.assert_called_once_with(
                "message_pinned", {"conversation_id": "456", "message_id": "123"}
            )

        @pytest.mark.asyncio
        async def test_handle_chat_action_unpin_message(self, processor, unpin_action_event_mock):
            """Test handling an unpin message chat action"""
            delta = {
                "conversation_id": "456",
                "unpinned_message_ids": ["123"]
            }
            processor.conversation_manager.update_conversation.return_value = delta
            processor.incoming_event_builder.pin_status_update = MagicMock(
                return_value={"event_type": "message_unpinned"}
            )

            result = await processor._handle_chat_action({"event": unpin_action_event_mock})

            assert len(result) == 1
            assert {"event_type": "message_unpinned"} in result

            processor.conversation_manager.update_conversation.assert_called_once_with({
                "event_type": "unpinned_message",
                "message": unpin_action_event_mock.original_update
            })
            processor.incoming_event_builder.pin_status_update.assert_called_once_with(
                "message_unpinned", {"conversation_id": "456", "message_id": "123"}
            )
