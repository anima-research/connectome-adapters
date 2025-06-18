import pytest
import json
import asyncio

from unittest.mock import AsyncMock, MagicMock, patch
from src.adapters.slack_adapter.event_processors.incoming_event_processor import (
    IncomingEventProcessor, SlackIncomingEventType
)
from src.adapters.slack_adapter.event_processors.history_fetcher import HistoryFetcher

class TestIncomingEventProcessor:
    """Tests for the Slack IncomingEventProcessor class"""

    @pytest.fixture
    def slack_client_mock(self):
        """Create a mocked Slack client"""
        client = AsyncMock()
        client.users_info = AsyncMock()
        return client

    @pytest.fixture
    def conversation_manager_mock(self):
        """Create a mocked conversation manager"""
        manager = AsyncMock()
        manager.add_to_conversation = AsyncMock(return_value=None)
        manager.update_conversation = AsyncMock(return_value=None)
        manager.delete_from_conversation = AsyncMock(return_value=None)
        manager.get_conversation = AsyncMock(return_value=None)
        return manager

    @pytest.fixture
    def downloader_mock(self):
        """Create a mocked downloader"""
        downloader = AsyncMock()
        downloader.download_attachments = AsyncMock(return_value=[])
        return downloader

    @pytest.fixture
    def rate_limiter_mock(self):
        """Create a mock rate limiter"""
        rate_limiter = AsyncMock()
        rate_limiter.limit_request = AsyncMock(return_value=None)
        rate_limiter.get_wait_time = AsyncMock(return_value=0)
        return rate_limiter

    @pytest.fixture
    def history_fetcher_mock(self):
        """Create a mock history fetcher"""
        fetcher = AsyncMock(spec=HistoryFetcher)
        fetcher.fetch = AsyncMock(return_value=[])
        return fetcher

    @pytest.fixture
    def processor(self,
                  slack_config,
                  slack_client_mock,
                  conversation_manager_mock,
                  downloader_mock,
                  rate_limiter_mock):
        """Create an IncomingEventProcessor with mocked dependencies"""
        processor = IncomingEventProcessor(
            slack_config, slack_client_mock, conversation_manager_mock
        )
        processor.downloader = downloader_mock
        processor.rate_limiter = rate_limiter_mock
        processor.incoming_event_builder = MagicMock()
        return processor

    @pytest.fixture
    def message_event_mock(self):
        """Create a mock for a new message event"""
        return {
            "type": SlackIncomingEventType.NEW_MESSAGE,
            "event": {
                "type": "message",
                "ts": "1662031200.123456",  # 2022-09-01 12:00:00
                "user": "U12345678",
                "text": "Test message",
                "channel": "C87654321",
                "team": "T11223344",
                "blocks": []
            }
        }

    @pytest.fixture
    def edited_message_event_mock(self):
        """Create a mock for an edited message event"""
        return {
            "type": SlackIncomingEventType.EDITED_MESSAGE,
            "event": {
                "type": "message",
                "subtype": "message_changed",
                "message": {
                    "type": "message",
                    "text": "Edited test message",
                    "user": "U12345678",
                    "team": "T11223344",
                    "edited": {
                        "user": "U12345678",
                        "ts": "1662031300.000000"  # A minute later
                    },
                    "ts": "1662031200.123456"
                },
                "previous_message": {
                    "type": "message",
                    "text": "Test message",
                    "user": "U12345678",
                    "ts": "1662031200.123456"
                },
                "channel": "C87654321",
                "ts": "1662031300.123457",
                "event_ts": "1662031300.123457",
                "team": "T11223344"
            }
        }

    @pytest.fixture
    def deleted_message_event_mock(self):
        """Create a mock for a deleted message event"""
        return {
            "type": SlackIncomingEventType.DELETED_MESSAGE,
            "event": {
                "type": "message",
                "subtype": "message_deleted",
                "previous_message": {
                    "type": "message",
                    "text": "Test message",
                    "user": "U12345678",
                    "ts": "1662031200.123456"
                },
                "channel": "C87654321",
                "ts": "1662031400.123458",  # 2 minutes later
                "deleted_ts": "1662031200.123456",
                "event_ts": "1662031400.123458",
                "team": "T11223344"
            }
        }

    @pytest.fixture
    def reaction_add_event_mock(self):
        """Create a mock for a reaction add event"""
        return {
            "type": SlackIncomingEventType.ADDED_REACTION,
            "event": {
                "type": "reaction_added",
                "user": "U12345678",
                "reaction": "thumbsup",
                "item": {
                    "type": "message",
                    "channel": "C87654321",
                    "ts": "1662031200.123456"
                },
                "item_user": "U12345678",
                "event_ts": "1662031500.123459",  # 5 minutes later
                "ts": "1662031500.123459",
                "team": "T11223344"
            }
        }

    @pytest.fixture
    def reaction_remove_event_mock(self):
        """Create a mock for a reaction remove event"""
        return {
            "type": SlackIncomingEventType.REMOVED_REACTION,
            "event": {
                "type": "reaction_removed",
                "user": "U12345678",
                "reaction": "thumbsup",
                "item": {
                    "type": "message",
                    "channel": "C87654321",
                    "ts": "1662031200.123456"
                },
                "item_user": "U12345678",
                "event_ts": "1662031600.123460",  # 6 minutes later
                "ts": "1662031600.123460",
                "team": "T11223344"
            }
        }

    @pytest.fixture
    def pin_add_event_mock(self):
        """Create a mock for a pin add event"""
        return {
            "type": SlackIncomingEventType.ADDED_PIN,
            "event": {
                "type": "pin_added",
                "user": "U12345678",
                "item": {
                    "type": "message",
                    "channel": "C87654321",
                    "ts": "1662031200.123456",
                    "message": {
                        "type": "message",
                        "text": "Test message",
                        "user": "U12345678",
                        "ts": "1662031200.123456"
                    }
                },
                "channel": "C87654321",
                "event_ts": "1662031700.123461",  # 7 minutes later
                "ts": "1662031700.123461",
                "team": "T11223344"
            }
        }

    @pytest.fixture
    def pin_remove_event_mock(self):
        """Create a mock for a pin remove event"""
        return {
            "type": SlackIncomingEventType.REMOVED_PIN,
            "event": {
                "type": "pin_removed",
                "user": "U12345678",
                "item": {
                    "type": "message",
                    "channel": "C87654321",
                    "ts": "1662031200.123456",
                    "message": {
                        "type": "message",
                        "text": "Test message",
                        "user": "U12345678",
                        "ts": "1662031200.123456"
                    }
                },
                "channel": "C87654321",
                "event_ts": "1662031800.123462",  # 8 minutes later
                "ts": "1662031800.123462",
                "team": "T11223344"
            }
        }

    @pytest.fixture
    def user_info_mock(self):
        """Create a mock user info response"""
        return {
            "ok": True,
            "user": {
                "id": "U12345678",
                "name": "testuser",
                "real_name": "Test User",
                "profile": {
                    "display_name": "Test User"
                }
            }
        }

    class TestProcessEvent:
        """Tests for the process_event method"""

        @pytest.mark.asyncio
        @pytest.mark.parametrize("event_type,expected_handler", [
            (SlackIncomingEventType.NEW_MESSAGE, "_handle_message"),
            (SlackIncomingEventType.EDITED_MESSAGE, "_handle_edited_message"),
            (SlackIncomingEventType.DELETED_MESSAGE, "_handle_deleted_message"),
            (SlackIncomingEventType.ADDED_REACTION, "_handle_reaction"),
            (SlackIncomingEventType.REMOVED_REACTION, "_handle_reaction"),
            (SlackIncomingEventType.ADDED_PIN, "_handle_pin"),
            (SlackIncomingEventType.REMOVED_PIN, "_handle_pin")
        ])
        async def test_process_event_calls_correct_handler(self,
                                                         processor,
                                                         event_type,
                                                         expected_handler):
            """Test that process_event calls the correct handler method"""
            event = {"type": event_type, "event": MagicMock()}
            handler_mocks = {}

            for handler_name in [
                "_handle_message",
                "_handle_edited_message",
                "_handle_deleted_message",
                "_handle_reaction",
                "_handle_pin"
            ]:
                handler_mock = AsyncMock(return_value=["event_info"])
                handler_mocks[handler_name] = handler_mock
                setattr(processor, handler_name, handler_mock)

            assert await processor.process_event(event) == ["event_info"]
            handler_mocks[expected_handler].assert_called_once_with(event)

        @pytest.mark.asyncio
        async def test_process_unknown_event(self, processor):
            """Test processing an unknown event type"""
            assert await processor.process_event({"type": "unknown_event"}) == []

        @pytest.mark.asyncio
        async def test_process_event_exception(self, processor, message_event_mock):
            """Test handling exceptions during event processing"""
            with patch.object(processor, "_handle_message", side_effect=Exception("Test error")):
                assert await processor.process_event(message_event_mock) == []

    class TestHandleMessage:
        """Tests for the _handle_message method"""

        @pytest.mark.asyncio
        @pytest.mark.filterwarnings("ignore::RuntimeWarning")
        async def test_handle_message(self, processor, message_event_mock, user_info_mock):
            """Test handling a new message"""
            message = {
                "conversation_id": "T11223344/C87654321",
                "message_id": "1662031200.123456",
                "text": "Test message",
                "sender": {"user_id": "U12345678", "display_name": "Test User"},
                "timestamp": 1662031200123,
                "attachments": []
            }
            delta = {
                "conversation_id": "T11223344/C87654321",
                "fetch_history": True,
                "added_messages": [message]
            }

            processor.client.users_info.return_value = user_info_mock
            processor.conversation_manager.add_to_conversation.return_value = delta

            with patch.object(HistoryFetcher, "fetch", return_value=[{"some": "history"}]):
                processor.incoming_event_builder.conversation_started = MagicMock(
                    return_value={"event_type": "conversation_started"}
                )
                processor.incoming_event_builder.history_fetched = MagicMock(
                    return_value={"event_type": "history_fetched"}
                )
                processor.incoming_event_builder.message_received = MagicMock(
                    return_value={"event_type": "message_received"}
                )

                result = await processor._handle_message(message_event_mock)

                assert len(result) == 3
                assert {"event_type": "conversation_started"} in result
                assert {"event_type": "history_fetched"} in result
                assert {"event_type": "message_received"} in result

                processor.client.users_info.assert_called_once_with(user="U12345678")
                processor.downloader.download_attachments.assert_called_once_with(message_event_mock["event"])
                processor.conversation_manager.add_to_conversation.assert_called_once()
                processor.incoming_event_builder.conversation_started.assert_called_once_with(delta)
                processor.incoming_event_builder.history_fetched.assert_called_once_with(delta, [{"some": "history"}])
                processor.incoming_event_builder.message_received.assert_called_once_with(message)

        @pytest.mark.asyncio
        async def test_handle_message_exception(self, processor, message_event_mock):
            """Test handling exceptions during message processing"""
            processor.conversation_manager.add_to_conversation.side_effect = Exception("Test error")
            assert await processor._handle_message(message_event_mock) == []

    class TestHandleEditedMessage:
        """Tests for the _handle_edited_message method"""

        @pytest.mark.asyncio
        @pytest.mark.filterwarnings("ignore::RuntimeWarning")
        async def test_handle_edited_message_content(self, processor, edited_message_event_mock):
            """Test handling an edited message (content change)"""
            message = {
                "conversation_id": "T11223344/C87654321",
                "message_id": "1662031200.123456",
                "text": "Edited test message",
                "timestamp": 1662031300123  # 2022-09-01 12:01:40
            }
            delta = {
                "conversation_id": "T11223344/C87654321",
                "updated_messages": [message]
            }

            processor.conversation_manager.update_conversation.return_value = delta
            processor.incoming_event_builder.message_updated = MagicMock(
                return_value={"event_type": "message_updated"}
            )

            result = await processor._handle_edited_message(edited_message_event_mock)

            assert len(result) == 1
            assert {"event_type": "message_updated"} in result

            processor.conversation_manager.update_conversation.assert_called_once_with({
                "event_type": "edited_message",
                "message": edited_message_event_mock["event"]
            })
            processor.incoming_event_builder.message_updated.assert_called_once_with(message)

        @pytest.mark.asyncio
        async def test_handle_edited_message_exception(self, processor, edited_message_event_mock):
            """Test handling exceptions during edited message processing"""
            processor.conversation_manager.update_conversation.side_effect = Exception("Test error")
            assert await processor._handle_edited_message(edited_message_event_mock) == []

    class TestHandleDeletedMessage:
        """Tests for the _handle_deleted_message method"""

        @pytest.mark.asyncio
        @pytest.mark.filterwarnings("ignore::RuntimeWarning")
        async def test_handle_deleted_message(self, processor, deleted_message_event_mock):
            """Test handling a deleted message"""
            delta = {
                "conversation_id": "T11223344/C87654321",
                "deleted_message_ids": ["1662031200.123456"]
            }

            processor.conversation_manager.delete_from_conversation.return_value = delta
            processor.incoming_event_builder.message_deleted = MagicMock(
                return_value={"event_type": "message_deleted"}
            )

            result = await processor._handle_deleted_message(deleted_message_event_mock)

            assert len(result) == 1
            assert {"event_type": "message_deleted"} in result

            processor.conversation_manager.delete_from_conversation.assert_called_once_with(
                incoming_event=deleted_message_event_mock["event"]
            )
            processor.incoming_event_builder.message_deleted.assert_called_once_with(
                "1662031200.123456", "T11223344/C87654321"
            )

        @pytest.mark.asyncio
        @pytest.mark.filterwarnings("ignore::RuntimeWarning")
        async def test_handle_deleted_message_exception(self, processor, deleted_message_event_mock):
            """Test handling exceptions during deleted message processing"""
            processor.conversation_manager.delete_from_conversation.side_effect = Exception("Test error")
            assert await processor._handle_deleted_message(deleted_message_event_mock) == []

    class TestHandleReaction:
        """Tests for the _handle_reaction method"""

        @pytest.mark.asyncio
        async def test_handle_reaction_add(self, processor, reaction_add_event_mock):
            """Test handling a reaction add event"""
            delta = {
                "conversation_id": "T11223344/C87654321",
                "message_id": "1662031200.123456",
                "added_reactions": ["thumbs_up"]
            }

            processor.conversation_manager.update_conversation.return_value = delta
            processor.incoming_event_builder.reaction_update = MagicMock(
                return_value={"event_type": "reaction_added"}
            )

            result = await processor._handle_reaction(reaction_add_event_mock)

            assert len(result) == 1
            assert {"event_type": "reaction_added"} in result

            processor.conversation_manager.update_conversation.assert_called_once_with({
                "event_type": "reaction",
                "message": reaction_add_event_mock["event"]
            })
            processor.incoming_event_builder.reaction_update.assert_called_once_with(
                "reaction_added", delta, "thumbs_up"
            )

        @pytest.mark.asyncio
        async def test_handle_reaction_remove(self, processor, reaction_remove_event_mock):
            """Test handling a reaction remove event"""
            delta = {
                "conversation_id": "T11223344/C87654321",
                "message_id": "1662031200.123456",
                "removed_reactions": ["thumbs_up"]
            }

            processor.conversation_manager.update_conversation.return_value = delta
            processor.incoming_event_builder.reaction_update = MagicMock(
                return_value={"event_type": "reaction_removed"}
            )

            result = await processor._handle_reaction(reaction_remove_event_mock)

            assert len(result) == 1
            assert {"event_type": "reaction_removed"} in result

            processor.conversation_manager.update_conversation.assert_called_once_with({
                "event_type": "reaction",
                "message": reaction_remove_event_mock["event"]
            })
            processor.incoming_event_builder.reaction_update.assert_called_once_with(
                "reaction_removed", delta, "thumbs_up"
            )

        @pytest.mark.asyncio
        @pytest.mark.filterwarnings("ignore::RuntimeWarning")
        async def test_handle_reaction_exception(self, processor, reaction_add_event_mock):
            """Test handling exceptions during reaction processing"""
            processor.conversation_manager.update_conversation.side_effect = Exception("Test error")
            assert await processor._handle_reaction(reaction_add_event_mock) == []

    class TestHandlePin:
        """Tests for the _handle_pin method"""

        @pytest.mark.asyncio
        async def test_handle_pin_add(self, processor, pin_add_event_mock):
            """Test handling a pin add event"""
            delta = {
                "conversation_id": "T11223344/C87654321",
                "message_id": "1662031200.123456",
                "pinned_message_ids": ["1662031200.123456"]
            }

            processor.conversation_manager.update_conversation.return_value = delta
            processor.incoming_event_builder.pin_status_update = MagicMock(
                return_value={"event_type": "message_pinned"}
            )

            result = await processor._handle_pin(pin_add_event_mock)

            assert len(result) == 1
            assert {"event_type": "message_pinned"} in result

            processor.conversation_manager.update_conversation.assert_called_once_with({
                "event_type": "pin",
                "message": pin_add_event_mock["event"]
            })
            processor.incoming_event_builder.pin_status_update.assert_called_once_with(
                "message_pinned",
                {
                    "message_id": "1662031200.123456",
                    "conversation_id": "T11223344/C87654321"
                }
            )

        @pytest.mark.asyncio
        @pytest.mark.filterwarnings("ignore::RuntimeWarning")
        async def test_handle_pin_remove(self, processor, pin_remove_event_mock):
            """Test handling a pin remove event"""
            delta = {
                "conversation_id": "T11223344/C87654321",
                "message_id": "1662031200.123456",
                "unpinned_message_ids": ["1662031200.123456"]
            }

            processor.conversation_manager.update_conversation.return_value = delta
            processor.incoming_event_builder.pin_status_update = MagicMock(
                return_value={"event_type": "message_unpinned"}
            )

            result = await processor._handle_pin(pin_remove_event_mock)

            assert len(result) == 1
            assert {"event_type": "message_unpinned"} in result

            processor.conversation_manager.update_conversation.assert_called_once_with({
                "event_type": "pin",
                "message": pin_remove_event_mock["event"]
            })
            processor.incoming_event_builder.pin_status_update.assert_called_once_with(
                "message_unpinned",
                {
                    "message_id": "1662031200.123456",
                    "conversation_id": "T11223344/C87654321"
                }
            )

        @pytest.mark.asyncio
        @pytest.mark.filterwarnings("ignore::RuntimeWarning")
        async def test_handle_pin_exception(self, processor, pin_add_event_mock):
            """Test handling exceptions during pin processing"""
            processor.conversation_manager.update_conversation.side_effect = Exception("Test error")
            assert await processor._handle_pin(pin_add_event_mock) == []

    class TestGetUserInfo:
        """Tests for the _get_user_info method"""

        @pytest.mark.asyncio
        async def test_get_user_info(self, processor, user_info_mock):
            """Test getting user info for a message"""
            processor.client.users_info.return_value = user_info_mock

            assert await processor._get_user_info({"user": "U12345678"}) == user_info_mock["user"]
            processor.client.users_info.assert_called_once_with(user="U12345678")

        @pytest.mark.asyncio
        async def test_get_user_info_exception(self, processor):
            """Test error handling in get_user_info"""
            processor.client.users_info.side_effect = Exception("Test error")

            assert await processor._get_user_info({"user": "U12345678"}) == {}
