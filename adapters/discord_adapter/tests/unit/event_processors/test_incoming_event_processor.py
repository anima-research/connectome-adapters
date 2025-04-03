import pytest
import discord

from unittest.mock import AsyncMock, MagicMock, patch
from adapters.discord_adapter.adapter.event_processors.incoming_event_processor import (
    IncomingEventProcessor, DiscordIncomingEventType
)

class TestIncomingEventProcessor:
    """Tests for the Discord IncomingEventProcessor class"""

    @pytest.fixture
    def discord_client_mock(self):
        """Create a mocked Discord client"""
        return AsyncMock()

    @pytest.fixture
    def conversation_manager_mock(self):
        """Create a mocked conversation manager"""
        manager = AsyncMock()
        manager.add_to_conversation = AsyncMock()
        manager.update_conversation = AsyncMock()
        manager.delete_from_conversation = AsyncMock()
        manager.get_conversation = AsyncMock()
        return manager

    @pytest.fixture
    def downloader_mock(self):
        """Create a mocked downloader"""
        downloader = AsyncMock()
        downloader.download_attachment = AsyncMock(return_value=[])
        return downloader

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
                  discord_client_mock,
                  conversation_manager_mock,
                  downloader_mock,
                  rate_limiter_mock):
        """Create an IncomingEventProcessor with mocked dependencies"""
        processor = IncomingEventProcessor(
            patch_config, discord_client_mock, conversation_manager_mock
        )
        processor.downloader = downloader_mock
        processor.rate_limiter = rate_limiter_mock
        return processor

    @pytest.fixture
    def message_event_mock(self):
        """Create a mock for a new message event"""
        message = MagicMock(spec=discord.Message)
        message.id = 123456789
        message.content = "Test message"
        message.created_at = MagicMock()
        message.created_at.timestamp.return_value = 1234567.89
        message.type = discord.MessageType.default

        # Author
        author = MagicMock()
        author.id = 987654321
        author.name = "Test User"
        message.author = author

        # Channel
        channel = MagicMock()
        channel.id = 111222333
        message.channel = channel

        # Guild
        guild = MagicMock()
        guild.id = 444555666
        message.guild = guild

        return {
            "type": DiscordIncomingEventType.NEW_MESSAGE,
            "event": message
        }

    @pytest.fixture
    def service_message_event_mock(self):
        """Create a mock for a service message event"""
        message = MagicMock(spec=discord.Message)
        message.id = 123456789
        message.content = "User joined the channel"
        message.created_at = MagicMock()
        message.created_at.timestamp.return_value = 1234567.89
        message.type = discord.MessageType.new_member  # Service message type

        # Author
        author = MagicMock()
        author.id = 987654321
        author.name = "Test User"
        message.author = author

        # Channel
        channel = MagicMock()
        channel.id = 111222333
        message.channel = channel

        return {
            "type": DiscordIncomingEventType.NEW_MESSAGE,
            "event": message
        }

    @pytest.fixture
    def edited_message_event_mock(self):
        """Create a mock for an edited message event"""
        message = MagicMock()
        message.id = 123456789
        message.message_id = 123456789
        message.channel_id = 111222333
        message.guild_id = 444555666
        message.data = {
            "content": "Edited test message",
            "edited_timestamp": "2023-01-01T12:00:00.000000+00:00",
            "pinned": False
        }

        return {
            "type": DiscordIncomingEventType.EDITED_MESSAGE,
            "event": message
        }

    @pytest.fixture
    def deleted_message_event_mock(self):
        """Create a mock for a deleted message event"""
        message = MagicMock()
        message.message_id = 123456789
        message.channel_id = 111222333
        message.guild_id = 444555666

        return {
            "type": DiscordIncomingEventType.DELETED_MESSAGE,
            "event": message
        }

    @pytest.fixture
    def reaction_add_event_mock(self):
        """Create a mock for a reaction add event"""
        reaction = MagicMock()
        reaction.message_id = 123456789
        reaction.channel_id = 111222333
        reaction.guild_id = 444555666

        emoji = MagicMock()
        emoji.name = "👍"
        reaction.emoji = emoji

        return {
            "type": DiscordIncomingEventType.ADDED_REACTION,
            "event": reaction
        }

    @pytest.fixture
    def reaction_remove_event_mock(self):
        """Create a mock for a reaction remove event"""
        reaction = MagicMock()
        reaction.message_id = 123456789
        reaction.channel_id = 111222333
        reaction.guild_id = 444555666

        emoji = MagicMock()
        emoji.name = "👍"
        reaction.emoji = emoji

        return {
            "type": DiscordIncomingEventType.REMOVED_REACTION,
            "event": reaction
        }

    class TestProcessEvent:
        """Tests for the process_event method"""

        @pytest.mark.asyncio
        @pytest.mark.parametrize("event_type,expected_handler", [
            (DiscordIncomingEventType.NEW_MESSAGE, "_handle_message"),
            (DiscordIncomingEventType.EDITED_MESSAGE, "_handle_edited_message"),
            (DiscordIncomingEventType.DELETED_MESSAGE, "_handle_deleted_message"),
            (DiscordIncomingEventType.ADDED_REACTION, "_handle_reaction"),
            (DiscordIncomingEventType.REMOVED_REACTION, "_handle_reaction")
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
                "_handle_reaction"
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
        async def test_handle_message(self, processor, message_event_mock):
            """Test handling a new message"""
            message = {
                "conversation_id": "444555666/111222333",
                "message_id": "123456789",
                "text": "Test message",
                "sender": {"user_id": "987654321", "display_name": "Test User"},
                "timestamp": 1234567890,
                "attachments": []
            }
            delta = {
                "conversation_id": "444555666/111222333",
                "fetch_history": True,
                "added_messages": [message]
            }

            processor.conversation_manager.add_to_conversation.return_value = delta
            processor._fetch_conversation_history = AsyncMock(
                return_value=[{"some": "history"}]
            )
            processor._conversation_started_event_info = AsyncMock(
                return_value={"event_type": "conversation_started"}
            )
            processor._new_message_event_info = AsyncMock(
                return_value={"event_type": "message_received"}
            )

            result = await processor._handle_message(message_event_mock)

            assert len(result) == 2
            assert {"event_type": "conversation_started"} in result
            assert {"event_type": "message_received"} in result

            processor.conversation_manager.add_to_conversation.assert_called_once()
            processor._fetch_conversation_history.assert_called_once_with(delta)
            processor._conversation_started_event_info.assert_called_once_with(
                delta, processor._fetch_conversation_history.return_value
            )
            processor._new_message_event_info.assert_called_once_with(message)

        @pytest.mark.asyncio
        async def test_handle_service_message(self, processor, service_message_event_mock):
            """Test handling a service message"""
            assert await processor._handle_message(service_message_event_mock) == []
            processor.conversation_manager.add_to_conversation.assert_not_called()

        @pytest.mark.asyncio
        async def test_handle_message_exception(self, processor, message_event_mock):
            """Test handling exceptions during message processing"""
            processor.conversation_manager.add_to_conversation.side_effect = Exception("Test error")
            assert await processor._handle_message(message_event_mock) == []

    class TestHandleEditedMessage:
        """Tests for the _handle_edited_message method"""

        @pytest.mark.asyncio
        async def test_handle_edited_message_content(self, processor, edited_message_event_mock):
            """Test handling an edited message (content change)"""
            message = {
                "conversation_id": "444555666/111222333",
                "message_id": "123456789",
                "text": "Edited test message",
                "timestamp": 1672574400000  # 2023-01-01T12:00:00
            }
            delta = {
                "conversation_id": "444555666/111222333",
                "updated_messages": [message]
            }

            processor.conversation_manager.update_conversation.return_value = delta
            processor._edited_message_event_info = AsyncMock(
                return_value={"event_type": "message_updated"}
            )

            result = await processor._handle_edited_message(edited_message_event_mock)

            assert len(result) == 1
            assert {"event_type": "message_updated"} in result

            processor.conversation_manager.update_conversation.assert_called_once_with({
                "event_type": "edited_message",
                "message": edited_message_event_mock["event"]
            })
            processor._edited_message_event_info.assert_called_once_with(message)

        @pytest.mark.asyncio
        async def test_handle_edited_message_pin(self, processor, edited_message_event_mock):
            """Test handling an edited message (pin status change)"""
            delta = {
                "conversation_id": "444555666/111222333",
                "pinned_message_ids": ["123456789"]
            }

            processor.conversation_manager.update_conversation.return_value = delta
            processor._pinned_status_change_event_info = AsyncMock(
                return_value={"event_type": "message_pinned"}
            )

            result = await processor._handle_edited_message(edited_message_event_mock)

            assert len(result) == 1
            assert {"event_type": "message_pinned"} in result

            processor._pinned_status_change_event_info.assert_called_once_with(
                "message_pinned",
                {
                    "message_id": "123456789",
                    "conversation_id": "444555666/111222333"
                }
            )

        @pytest.mark.asyncio
        async def test_handle_edited_message_unpin(self, processor, edited_message_event_mock):
            """Test handling an edited message (unpin)"""
            delta = {
                "conversation_id": "444555666/111222333",
                "unpinned_message_ids": ["123456789"]
            }

            processor.conversation_manager.update_conversation.return_value = delta
            processor._pinned_status_change_event_info = AsyncMock(
                return_value={"event_type": "message_unpinned"}
            )

            result = await processor._handle_edited_message(edited_message_event_mock)

            assert len(result) == 1
            assert {"event_type": "message_unpinned"} in result

            processor._pinned_status_change_event_info.assert_called_once_with(
                "message_unpinned",
                {
                    "message_id": "123456789",
                    "conversation_id": "444555666/111222333"
                }
            )

        @pytest.mark.asyncio
        async def test_handle_edited_message_exception(self, processor, edited_message_event_mock):
            """Test handling exceptions during edited message processing"""
            processor.conversation_manager.update_conversation.side_effect = Exception("Test error")
            assert await processor._handle_edited_message(edited_message_event_mock) == []

    class TestHandleDeletedMessage:
        """Tests for the _handle_deleted_message method"""

        @pytest.mark.asyncio
        async def test_handle_deleted_message(self, processor, deleted_message_event_mock):
            """Test handling a deleted message"""
            delta = {
                "conversation_id": "444555666/111222333",
                "deleted_message_ids": ["123456789"]
            }

            processor.conversation_manager.delete_from_conversation.return_value = delta
            processor._deleted_message_event_info = AsyncMock(
                return_value={"event_type": "message_deleted"}
            )

            result = await processor._handle_deleted_message(deleted_message_event_mock)

            assert len(result) == 1
            assert {"event_type": "message_deleted"} in result

            processor.conversation_manager.delete_from_conversation.assert_called_once_with(
                incoming_event=deleted_message_event_mock["event"]
            )
            processor._deleted_message_event_info.assert_called_once_with(
                "123456789", "444555666/111222333"
            )

        @pytest.mark.asyncio
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
                "conversation_id": "444555666/111222333",
                "message_id": "123456789",
                "added_reactions": ["thumbs_up"]
            }

            processor.conversation_manager.update_conversation.return_value = delta
            processor._reaction_update_event_info = AsyncMock(
                return_value={"event_type": "reaction_added"}
            )

            result = await processor._handle_reaction(reaction_add_event_mock)

            assert len(result) == 1
            assert {"event_type": "reaction_added"} in result

            processor.conversation_manager.update_conversation.assert_called_once_with({
                "event_type": reaction_add_event_mock["type"],
                "message": reaction_add_event_mock["event"]
            })
            processor._reaction_update_event_info.assert_called_once_with(
                "reaction_added", delta, "thumbs_up"
            )

        @pytest.mark.asyncio
        async def test_handle_reaction_remove(self, processor, reaction_remove_event_mock):
            """Test handling a reaction remove event"""
            delta = {
                "conversation_id": "444555666/111222333",
                "message_id": "123456789",
                "removed_reactions": ["thumbs_up"]
            }

            processor.conversation_manager.update_conversation.return_value = delta
            processor._reaction_update_event_info = AsyncMock(
                return_value={"event_type": "reaction_removed"}
            )

            result = await processor._handle_reaction(reaction_remove_event_mock)

            assert len(result) == 1
            assert {"event_type": "reaction_removed"} in result

            processor.conversation_manager.update_conversation.assert_called_once_with({
                "event_type": reaction_remove_event_mock["type"],
                "message": reaction_remove_event_mock["event"]
            })
            processor._reaction_update_event_info.assert_called_once_with(
                "reaction_removed", delta, "thumbs_up"
            )

        @pytest.mark.asyncio
        async def test_handle_reaction_exception(self, processor, reaction_add_event_mock):
            """Test handling exceptions during reaction processing"""
            processor.conversation_manager.update_conversation.side_effect = Exception("Test error")
            assert await processor._handle_reaction(reaction_add_event_mock) == []
