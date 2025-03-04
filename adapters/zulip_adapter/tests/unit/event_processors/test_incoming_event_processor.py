import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json

from adapters.zulip_adapter.adapter.event_processors.incoming_event_processor import (
    IncomingEventProcessor, ZulipIncomingEventType
)

class TestIncomingEventProcessor:
    """Tests for the ZulipIncomingEventProcessor class"""

    @pytest.fixture
    def zulip_client_mock(self):
        """Create a mocked Zulip client"""
        return AsyncMock()

    @pytest.fixture
    def conversation_manager_mock(self):
        """Create a mocked conversation manager"""
        manager = AsyncMock()
        manager.add_to_conversation = AsyncMock()
        manager.update_conversation = AsyncMock()
        manager.migrate_between_conversations = AsyncMock()
        return manager

    @pytest.fixture
    def rate_limiter_mock(self):
        """Create a mock rate limiter"""
        rate_limiter = AsyncMock()
        rate_limiter.limit_request = AsyncMock(return_value=None)
        rate_limiter.get_wait_time = AsyncMock(return_value=0)
        return rate_limiter

    @pytest.fixture
    def processor(self,
                  patch_config,
                  zulip_client_mock,
                  conversation_manager_mock,
                  rate_limiter_mock):
        """Create a ZulipIncomingEventProcessor with mocked dependencies"""
        processor = IncomingEventProcessor(
            patch_config, zulip_client_mock, conversation_manager_mock
        )
        processor.rate_limiter = rate_limiter_mock
        return processor

    @pytest.fixture
    def message_event_mock(self):
        """Create a mock for a new message event"""
        return {
            "type": "message",
            "message": {
                "id": 123,
                "content": "Test message",
                "sender_id": 456,
                "sender_full_name": "Test User",
                "timestamp": 1234567890,
                "type": "private",
                "display_recipient": [
                    {"id": 456, "email": "test@example.com", "full_name": "Test User"},
                    {"id": 789, "email": "bot@example.com", "full_name": "Test Bot"}
                ]
            }
        }

    @pytest.fixture
    def update_message_event_mock(self):
        """Create a mock for an update message event"""
        return {
            "type": "update_message",
            "message_id": 123,
            "orig_content": "Test message",
            "content": "Edited test message",
            "user_id": 456,
            "timestamp": 1234567890
        }

    @pytest.fixture
    def delete_message_event_mock(self):
        """Create a mock for an delete message event"""
        return {
            "type": "delete_message",
            "message_type": "private",
            "message_id": 123
        }

    @pytest.fixture
    def topic_change_event_mock(self):
        """Create a mock for a topic change event"""
        return {
            "type": "update_message",
            "message_id": 123,
            "stream_id": 456,
            "subject": "new topic",
            "orig_subject": "old topic",
            "message_ids": [123, 456]
        }

    class TestProcessEvent:
        """Tests for the process_event method"""

        @pytest.mark.asyncio
        @pytest.mark.parametrize("event_type,event_key", [
            (ZulipIncomingEventType.MESSAGE, "message"),
            (ZulipIncomingEventType.UPDATE_MESSAGE, "update_message"),
            (ZulipIncomingEventType.DELETE_MESSAGE, "delete_message"),
            (ZulipIncomingEventType.REACTION, "reaction")
        ])
        async def test_process_event_calls_correct_handler(self, processor, event_type, event_key):
            """Test that process_event calls the correct handler method"""
            event = {"type": event_type}
            handler_mocks = {}

            for handler_type in ZulipIncomingEventType:
                method_name = f"_handle_{handler_type.value}"
                handler_mock = AsyncMock(return_value=["event_info"])
                handler_mocks[handler_type] = handler_mock
                setattr(processor, method_name, handler_mock)

            assert await processor.process_event(event) == ["event_info"]
            handler_mocks[event_type].assert_called_once_with(event)

        @pytest.mark.asyncio
        async def test_process_unknown_event(self, processor):
            """Test processing an unknown event type"""
            assert await processor.process_event({"type": "unknown_event"}) == []

        @pytest.mark.asyncio
        async def test_process_event_exception(self, processor, message_event_mock):
            """Test handling exceptions during event processing"""
            with patch.object(processor, "_handle_message", side_effect=Exception("Test error")):
                assert await processor.process_event(message_event_mock) == []

    class TestHandleMessageEvent:
        """Tests for the _handle_message method"""

        @pytest.mark.asyncio
        async def test_handle_message(self, processor, message_event_mock):
            """Test handling a new message"""
            message = {
                "conversation_id": "456_789",
                "message_id": "123",
                "text": "Test message",
                "sender": {"user_id": "456", "display_name": "Test User"},
                "timestamp": 1234567890000,
                "attachments": []
            }
            delta = {
                "fetch_history": True,
                "added_messages": [message]
            }

            processor.conversation_manager.add_to_conversation.return_value = delta
            processor._fetch_conversation_history = AsyncMock(return_value=[{"some": "history"}])
            processor._conversation_started_event_info = AsyncMock(
                return_value={"event_type": "conversation_started"}
            )
            processor._new_message_event_info = AsyncMock(return_value={"event_type": "message_received"})

            result = await processor._handle_message(message_event_mock)

            assert len(result) == 2
            assert {"event_type": "conversation_started"} in result
            assert {"event_type": "message_received"} in result

            processor.conversation_manager.add_to_conversation.assert_called_once_with(
                {"message": message_event_mock.get("message"), "attachments": []}
            )

            processor._fetch_conversation_history.assert_called_once()
            processor._conversation_started_event_info.assert_called_once_with(
                delta, processor._fetch_conversation_history.return_value
            )
            processor._new_message_event_info.assert_called_once_with(message)

        @pytest.mark.asyncio
        async def test_handle_message_no_delta(self, processor, message_event_mock):
            """Test handling a message with no conversation delta"""
            processor.conversation_manager.add_to_conversation.return_value = None
            assert await processor._handle_message(message_event_mock) == []

        @pytest.mark.asyncio
        async def test_handle_message_exception(self, processor, message_event_mock):
            """Test handling exceptions during message processing"""
            processor.conversation_manager.add_to_conversation.side_effect = Exception("Test error")
            assert await processor._handle_message(message_event_mock) == []

    class TestHandleUpdateMessageEvent:
        """Tests for the _handle_update_message method"""

        @pytest.mark.asyncio
        async def test_handle_message_update(self, processor, update_message_event_mock):
            """Test handling an updated message"""
            processor._is_topic_change = MagicMock(return_value=False)

            expected_result = [{"test": "message_change_result"}]
            processor._handle_message_change = AsyncMock(return_value=expected_result)

            assert await processor._handle_update_message(update_message_event_mock) == expected_result
            processor._is_topic_change.assert_called_once_with(update_message_event_mock)
            processor._handle_message_change.assert_called_once_with(update_message_event_mock)

        @pytest.mark.asyncio
        async def test_handle_message_change_success(self, processor, update_message_event_mock):
            """Test handling a message content change"""
            message = {
                "conversation_id": "456_789",
                "message_id": "123",
                "text": "Edited test message",
                "timestamp": 1234567890000
            }
            delta = {
                "updated_messages": [message]
            }

            processor.conversation_manager.update_conversation.return_value = delta
            processor._edited_message_event_info = AsyncMock(
                return_value={"event_type": "message_updated"}
            )

            result = await processor._handle_message_change(update_message_event_mock)

            assert len(result) == 1
            assert {"event_type": "message_updated"} in result

            processor.conversation_manager.update_conversation.assert_called_once_with({
                "event_type": "update_message",
                "message": update_message_event_mock,
                "attachments": []
            })
            processor._edited_message_event_info.assert_called_once_with(message)

        @pytest.mark.asyncio
        async def test_handle_topic_change_update(self, processor, topic_change_event_mock):
            """Test handling a message update that's a topic change"""
            processor._is_topic_change = MagicMock(return_value=True)

            expected_result = [{"test": "topic_change_result"}]
            processor._handle_topic_change = AsyncMock(return_value=expected_result)

            assert await processor._handle_update_message(topic_change_event_mock) == expected_result
            processor._is_topic_change.assert_called_once_with(topic_change_event_mock)
            processor._handle_topic_change.assert_called_once_with(topic_change_event_mock)

        @pytest.mark.asyncio
        async def test_handle_topic_change_success(self, processor, topic_change_event_mock):
            """Test successful handling of topic change"""
            delta = {
                "fetch_history": True,
                "conversation_id": "456/new topic",
                "deleted_message_ids": ["123", "987"],
                "added_messages": [{
                    "conversation_id": "456/new topic",
                    "message_id": "123",
                    "text": "Migrated text message",
                    "sender": {"user_id": "456", "display_name": "Test User"},
                    "timestamp": 1234567890000,
                    "attachments": []
                }]
            }

            processor.conversation_manager.migrate_between_conversations.return_value = delta
            processor._fetch_conversation_history = AsyncMock(return_value=[])
            processor._conversation_started_event_info = AsyncMock(
                return_value={"event_type": "conversation_started"}
            )
            processor._deleted_message_event_info = AsyncMock(
                return_value={"event_type": "message_deleted"}
            )
            processor._new_message_event_info = AsyncMock(
                return_value={"event_type": "message_received"}
            )

            result = await processor._handle_topic_change(topic_change_event_mock)

            # Should have 3 events: 1 conversation_started, 2 message_deleted, 1 message_received
            assert len(result) == 4

            event_types = [event.get("event_type") for event in result]
            assert "conversation_started" in event_types
            assert "message_deleted" in event_types
            assert "message_received" in event_types

            processor.conversation_manager.migrate_between_conversations.assert_called_once_with(
                topic_change_event_mock
            )
            assert processor._deleted_message_event_info.call_count == 2
            assert processor._new_message_event_info.call_count == 1

    class TestHandleDeleteMessageEvent:
        """Tests for the _handle_delete_message method"""

        @pytest.mark.asyncio
        async def test_handle_delete_message_success(self, processor, delete_message_event_mock):
            """Test handling a message content change"""
            delta = {
                "conversation_id": "456_789",
                "deleted_message_ids": ["123"]
            }

            processor.conversation_manager.delete_from_conversation.return_value = delta
            processor._deleted_message_event_info = AsyncMock(
                return_value={"event_type": "message_deleted"}
            )

            result = await processor._handle_delete_message(delete_message_event_mock)

            assert len(result) == 1
            assert {"event_type": "message_deleted"} in result

            processor.conversation_manager.delete_from_conversation.assert_called_once_with(
                incoming_event=delete_message_event_mock
            )
            processor._deleted_message_event_info.assert_called_once_with("123", "456_789")

        @pytest.mark.asyncio
        async def test_handle_delete_message_exception(self, processor, message_event_mock):
            """Test handling exceptions during message processing"""
            processor.conversation_manager.delete_from_conversation.side_effect = Exception("Test error")
            assert await processor._handle_delete_message(message_event_mock) == []

    class TestHandleReaction:
        """Tests for the _handle_reaction method"""

        @pytest.fixture
        def reaction_event_mock(self):
            """Create a mock for a reaction event"""
            return {
                "type": "reaction",
                "user_id": 456,
                "message_id": 123,
                "emoji_name": "+1",
                "emoji_code": "1f44d",
                "reaction_type": "unicode_emoji"
            }

        @pytest.mark.asyncio
        @pytest.mark.filterwarnings("ignore::RuntimeWarning")
        async def test_handle_reaction_added(self, processor, reaction_event_mock):
            """Test handling a reaction added event"""
            reaction_event_mock["op"] = "add"
            delta = {
                "updates": ["reaction_added"],
                "conversation_id": "456_789",
                "message_id": "123",
                "added_reactions": ["👍"],
                "timestamp": 1234567890000
            }
            processor.conversation_manager.update_conversation.return_value = delta
            processor._reaction_update_event_info = AsyncMock(
                return_value={"event_type": "reaction_added"}
            )
            result = await processor._handle_reaction(reaction_event_mock)

            assert len(result) == 1
            assert {"event_type": "reaction_added"} in result

            processor.conversation_manager.update_conversation.assert_called_once_with(
                {"event_type": "reaction", "message": reaction_event_mock}
            )
            processor._reaction_update_event_info.assert_called_once_with(
                "reaction_added", delta, "👍"
            )

        @pytest.mark.asyncio
        @pytest.mark.filterwarnings("ignore::RuntimeWarning")
        async def test_handle_reaction_removed(self, processor, reaction_event_mock):
            """Test handling a reaction removed event"""
            reaction_event_mock["op"] = "remove"
            delta = {
                "updates": ["reaction_removed"],
                "conversation_id": "456_789",
                "message_id": "123",
                "removed_reactions": ["👍"],
                "timestamp": 1234567890000
            }
            processor.conversation_manager.update_conversation.return_value = delta
            processor._reaction_update_event_info = AsyncMock(
                return_value={"event_type": "reaction_removed"}
            )
            result = await processor._handle_reaction(reaction_event_mock)

            assert len(result) == 1
            assert {"event_type": "reaction_removed"} in result

            processor.conversation_manager.update_conversation.assert_called_once_with(
                {"event_type": "reaction", "message": reaction_event_mock}
            )
            processor._reaction_update_event_info.assert_called_once_with(
                "reaction_removed", delta, "👍"
            )

        @pytest.mark.asyncio
        async def test_handle_reaction_no_delta(self, processor, reaction_event_mock):
            """Test handling a reaction with no delta"""
            reaction_event_mock["op"] = "remove"
            processor.conversation_manager.update_conversation.return_value = None

            assert await processor._handle_reaction(reaction_event_mock) == []

        @pytest.mark.asyncio
        async def test_handle_reaction_exception(self, processor, reaction_event_mock):
            """Test handling exceptions during reaction processing"""
            reaction_event_mock["op"] = "remove"
            processor.conversation_manager.update_conversation.side_effect = Exception("Test error")

            assert await processor._handle_reaction(reaction_event_mock) == []

    class TestHelperMethods:
        """Tests for helper methods"""

        @pytest.mark.asyncio
        async def test_conversation_started_event_info(self, processor):
            """Test creating a conversation started event"""
            delta = {"conversation_id": "456_789"}
            history = [{"message_id": "1", "text": "Test history message"}]
            result = await processor._conversation_started_event_info(delta, history)

            assert result["adapter_type"] == "zulip"
            assert result["event_type"] == "conversation_started"
            assert result["data"]["conversation_id"] == "456_789"
            assert result["data"]["history"] == history

        @pytest.mark.asyncio
        async def test_new_message_event_info(self, processor):
            """Test creating a new message event"""
            result = await processor._new_message_event_info({
                "message_id": "123",
                "conversation_id": "456_789",
                "text": "Hello, world!",
                "sender": {"user_id": "456", "display_name": "Test User"},
                "timestamp": 1234567890000,
                "attachments": [{"type": "image"}],
                "thread_id": "thread123"
            })

            assert result["adapter_type"] == "zulip"
            assert result["event_type"] == "message_received"
            assert result["data"]["adapter_name"] == "test_bot"
            assert result["data"]["message_id"] == "123"
            assert result["data"]["conversation_id"] == "456_789"
            assert result["data"]["text"] == "Hello, world!"
            assert result["data"]["sender"]["user_id"] == "456"
            assert result["data"]["sender"]["display_name"] == "Test User"
            assert result["data"]["timestamp"] == 1234567890000
            assert len(result["data"]["attachments"]) == 1
            assert result["data"]["thread_id"] == "thread123"

        @pytest.mark.asyncio
        async def test_edited_message_event_info(self, processor):
            """Test creating an edited message event"""
            result = await processor._edited_message_event_info({
                "message_id": "123",
                "conversation_id": "456_789",
                "text": "Edited message",
                "timestamp": 1234567890000
            })

            assert result["adapter_type"] == "zulip"
            assert result["event_type"] == "message_updated"
            assert result["data"]["adapter_name"] == "test_bot"
            assert result["data"]["message_id"] == "123"
            assert result["data"]["conversation_id"] == "456_789"
            assert result["data"]["new_text"] == "Edited message"
            assert result["data"]["timestamp"] == 1234567890000

        @pytest.mark.asyncio
        async def test_deleted_message_event_info(self, processor):
            """Test creating a deleted message event"""
            result = await processor._deleted_message_event_info(123, "456/old topic")

            assert result["adapter_type"] == "zulip"
            assert result["event_type"] == "message_deleted"
            assert result["data"]["message_id"] == "123"
            assert result["data"]["conversation_id"] == "456/old topic"

        @pytest.mark.asyncio
        async def test_reaction_update_event_info(self, processor):
            """Test creating a reaction event"""
            result = await processor._reaction_update_event_info(
                "reaction_added",
                {
                    "message_id": "123",
                    "conversation_id": "456_789"
                },
                "👍"
            )

            assert result["adapter_type"] == "zulip"
            assert result["event_type"] == "reaction_added"
            assert result["data"]["message_id"] == "123"
            assert result["data"]["conversation_id"] == "456_789"
            assert result["data"]["emoji"] == "👍"
