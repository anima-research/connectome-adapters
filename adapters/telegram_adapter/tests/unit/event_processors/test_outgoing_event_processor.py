import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from enum import Enum
from telethon.tl.types import ReactionEmoji

from adapters.telegram_adapter.adapter.attachment_loaders.uploader import Uploader
from adapters.telegram_adapter.adapter.conversation.manager import Manager
from adapters.telegram_adapter.adapter.event_processors.outgoing_event_processor import OutgoingEventProcessor
from core.events.processors.base_outgoing_event_processor import OutgoingEventType

class TestOutgoingEventProcessor:
    """Tests for the OutgoingEventProcessor class"""

    @pytest.fixture
    def telethon_client_mock(self):
        """Create a mocked Telethon client"""
        client = AsyncMock()
        client.client = AsyncMock()
        client.send_message = AsyncMock()
        client.edit_message = AsyncMock()
        client.delete_messages = AsyncMock()
        client.get_messages = AsyncMock()
        client.get_entity = AsyncMock()
        return client

    @pytest.fixture
    def conversation_manager_mock(self):
        """Create a mocked conversation manager"""
        manager = AsyncMock()
        manager.add_to_conversation = AsyncMock()
        manager.update_conversation = AsyncMock()
        manager.delete_from_conversation = AsyncMock()
        manager.get_conversation = MagicMock()
        manager.get_conversation_member = MagicMock()
        manager.conversations = {}
        return manager

    @pytest.fixture
    def uploader_mock(self):
        """Create a mocked uploader"""
        uploader = AsyncMock()
        uploader.upload_attachment = AsyncMock()
        return uploader

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
                  telethon_client_mock,
                  conversation_manager_mock,
                  uploader_mock,
                  rate_limiter_mock):
        """Create a SocketIoEventsProcessor with mocked dependencies"""
        with patch.object(Uploader, "__new__") as UploaderMock:
            UploaderMock.return_value = uploader_mock
            processor = OutgoingEventProcessor(patch_config, telethon_client_mock, conversation_manager_mock)
            processor.rate_limiter = rate_limiter_mock
            return processor

    @pytest.fixture
    def message_mock(self):
        """Create a mock message object"""
        message = MagicMock()
        message.id = 123
        message.chat_id = 456
        message.text = "Test message"
        return message

    @pytest.fixture
    def reaction_mock(self):
        """Create a mock reaction object"""
        reaction = MagicMock()
        results = []

        for emoji in ["👍", "❤️"]:
            result = MagicMock()
            result.reaction = MagicMock()
            result.reaction.emoticon = emoji
            results.append(result)

        reaction.results = results
        return reaction

    class TestSendMessage:
        """Tests for the send_message method"""

        @pytest.mark.asyncio
        async def test_send_message_success(self,
                                            processor,
                                            telethon_client_mock,
                                            message_mock,
                                            uploader_mock):
            """Test sending a message with attachments"""
            telethon_client_mock.send_message.return_value = message_mock
            telethon_client_mock.get_entity.return_value = "entity"

            attachment_info = {
                "message": MagicMock(),
                "attachment_id": "some_id",
                "attachment_type": "document",
                "file_extension": "txt",
                "size": 12345,
                "processable": True,
                "content": None
            }
            uploader_mock.upload_attachment.return_value = attachment_info

            event_data = {
                "event_type": "send_message",
                "data": {
                    "conversation_id": "123",
                    "text": "Hello, world!",
                    "attachments": [
                        {"file_name": "some_file.txt", "content": "dGVzdAo="}
                    ]
                }
            }

            with patch("asyncio.sleep"):
                response = await processor.process_event(event_data)
                assert response["request_completed"] is True

            telethon_client_mock.send_message.assert_called_once_with(
                entity="entity",
                message="Hello, world!",
                reply_to=None
            )
            uploader_mock.upload_attachment.assert_called_once()
            assert processor.conversation_manager.add_to_conversation.call_count == 2

        @pytest.mark.asyncio
        async def test_send_message_missing_required_fields(self, processor):
            """Test sending a message with missing required fields"""
            # Missing conversation_id
            response = await processor.process_event({
                "event_type": "send_message",
                "data": {"text": "Hello"}
            })
            assert response["request_completed"] is False

            # Missing text
            response = await processor.process_event({
                "event_type": "send_message",
                "data": {"conversation_id": "123"}
            })
            assert response["request_completed"] is False

        @pytest.mark.asyncio
        async def test_send_message_entity_not_found(self, processor, telethon_client_mock):
            """Test sending a message when entity can't be found"""
            telethon_client_mock.get_entity.return_value = None
            response = await processor.process_event({
                "event_type": "send_message",
                "data": {"conversation_id": "123", "text": "Hello, world!"}
            })

            assert response["request_completed"] is False
            telethon_client_mock.send_message.assert_not_called()

        @pytest.mark.asyncio
        async def test_send_message_exception(self, processor, telethon_client_mock):
            """Test handling an exception during send_message"""
            telethon_client_mock.get_entity.side_effect = Exception("Test error")
            response = await processor.process_event({
                "event_type": "send_message",
                "data": {"conversation_id": "123", "text": "Hello, world!"}
            })

            assert response["request_completed"] is False

    class TestEditMessage:
        """Tests for the edit_message method"""

        @pytest.mark.asyncio
        async def test_edit_message_success(self, processor, telethon_client_mock, message_mock):
            """Test successfully editing a message"""
            telethon_client_mock.edit_message.return_value = message_mock
            telethon_client_mock.get_entity.return_value = "entity"

            response = await processor.process_event({
                "event_type": "edit_message",
                "data": {
                    "conversation_id": "123",
                    "message_id": "456",
                    "text": "Updated text"
                }
            })

            assert response["request_completed"] is True
            telethon_client_mock.edit_message.assert_called_once_with(
                entity="entity",
                message=456,  # Should be converted to int
                text="Updated text"
            )
            processor.conversation_manager.update_conversation.assert_called_once_with({
                "event_type": "edited_message",
                "message": message_mock
            })

        @pytest.mark.asyncio
        async def test_edit_message_missing_required_fields(self, processor):
            """Test editing a message with missing required fields"""
            # Missing conversation_id
            response = await processor.process_event({
                "event_type": "edit_message",
                "data": {"message_id": "123", "text": "Hello"}
            })
            assert response["request_completed"] is False

            # Missing message_id
            response = await processor.process_event({
                "event_type": "edit_message",
                "data": {"conversation_id": "123", "text": "Hello"}
            })
            assert response["request_completed"] is False

            # Missing text
            response = await processor.process_event({
                "event_type": "edit_message",
                "data": {"conversation_id": "123", "message_id": "456"}
            })
            assert response["request_completed"] is False

        @pytest.mark.asyncio
        async def test_edit_message_entity_not_found(self, processor, telethon_client_mock):
            """Test editing a message when entity can't be found"""
            telethon_client_mock.get_entity.return_value = None
            response = await processor.process_event({
                "event_type": "edit_message",
                "data": {
                    "conversation_id": "123",
                    "message_id": "456",
                    "text": "Updated text"
                }
            })

            assert response["request_completed"] is False
            telethon_client_mock.edit_message.assert_not_called()

        @pytest.mark.asyncio
        async def test_edit_message_exception(self, processor, telethon_client_mock):
            """Test handling an exception during edit_message"""
            telethon_client_mock.get_entity.side_effect = Exception("Test error")
            response = await processor.process_event({
                "event_type": "edit_message",
                "data": {
                    "conversation_id": "123",
                    "message_id": "456",
                    "text": "Updated text"
                }
            })

            assert response["request_completed"] is False

    class TestDeleteMessage:
        """Tests for the delete_message method"""

        @pytest.mark.asyncio
        async def test_delete_message_success(self, processor, telethon_client_mock):
            """Test successfully deleting a message"""
            telethon_client_mock.delete_messages.return_value = [MagicMock()]
            telethon_client_mock.get_entity.return_value = "entity"
            response = await processor.process_event({
                "event_type": "delete_message",
                "data": {
                    "conversation_id": "123",
                    "message_id": "456"
                }
            })

            assert response["request_completed"] is True
            telethon_client_mock.delete_messages.assert_called_once_with(
                entity="entity",
                message_ids=[456]  # Should be converted to int
            )
            processor.conversation_manager.delete_from_conversation.assert_called_once_with(
                outgoing_event={
                    "deleted_ids": ["456"],
                    "conversation_id": "123"
                }
            )

        @pytest.mark.asyncio
        async def test_delete_message_missing_required_fields(self, processor):
            """Test deleting a message with missing required fields"""
            # Missing conversation_id
            response = await processor.process_event({
                "event_type": "delete_message",
                "data": {"message_id": "123"}
            })
            assert response["request_completed"] is False

            # Missing message_id
            response = await processor.process_event({
                "event_type": "delete_message",
                "data": {"conversation_id": "123"}
            })
            assert response["request_completed"] is False

        @pytest.mark.asyncio
        async def test_delete_message_entity_not_found(self, processor, telethon_client_mock):
            """Test deleting a message when entity can't be found"""
            telethon_client_mock.get_entity.return_value = None
            response = await processor.process_event({
                "event_type": "delete_message",
                "data": {
                    "conversation_id": "123",
                    "message_id": "456"
                }
            })

            assert response["request_completed"] is False
            telethon_client_mock.delete_messages.assert_not_called()

        @pytest.mark.asyncio
        async def test_delete_message_exception(self, processor, telethon_client_mock):
            """Test handling an exception during delete_message"""
            telethon_client_mock.get_entity.side_effect = Exception("Test error")
            response = await processor.process_event({
                "event_type": "delete_message",
                "data": {
                    "conversation_id": "123",
                    "message_id": "456"
                }
            })

            assert response["request_completed"] is False

    class TestReactions:
        """Tests for reaction-related methods"""

        @pytest.mark.asyncio
        async def test_add_reaction_success(self, processor, telethon_client_mock, message_mock):
            """Test successfully adding a reaction"""
            telethon_client_mock.return_value = message_mock
            telethon_client_mock.get_entity.return_value = "entity"
            response = await processor.process_event({
                "event_type": "add_reaction",
                "data": {
                    "conversation_id": "123",
                    "message_id": "456",
                    "emoji": "thumbs_up"
                }
            })

            assert response["request_completed"] is True
            processor.conversation_manager.update_conversation.assert_called_once_with({
                "event_type": "edited_message",
                "message": message_mock
            })

        @pytest.mark.asyncio
        async def test_remove_reaction_success(self,
                                               processor,
                                               telethon_client_mock,
                                               message_mock,
                                               reaction_mock):
            """Test successfully removing a reaction"""
            telethon_client_mock.return_value = message_mock
            telethon_client_mock.get_entity.return_value = "entity"

            old_message = MagicMock()
            old_message.reactions = reaction_mock
            telethon_client_mock.get_messages.return_value = old_message

            event_data = {
                "event_type": "remove_reaction",
                "data": {
                    "conversation_id": "123",
                    "message_id": "456",
                    "emoji": "thumbs_up"
                }
            }

            with patch.object(processor, "_update_reactions_list") as mock_update_reactions:
                mock_update_reactions.return_value = [ReactionEmoji(emoticon="❤️")]
                response = await processor.process_event(event_data)
                assert response["request_completed"] is True

            telethon_client_mock.get_messages.assert_called_once_with("entity", ids=456)
            mock_update_reactions.assert_called_once_with(reaction_mock, "👍")
            processor.conversation_manager.update_conversation.assert_called_once_with({
                "event_type": "edited_message",
                "message": message_mock
            })

        @pytest.mark.asyncio
        async def test_remove_reaction_no_reactions(self, processor, telethon_client_mock):
            """Test removing a reaction from a message with no reactions"""
            telethon_client_mock.get_entity.return_value = "entity"

            old_message = MagicMock()
            old_message.reactions = None
            telethon_client_mock.get_messages.return_value = old_message

            response = await processor.process_event({
                "event_type": "remove_reaction",
                "data": {
                    "conversation_id": "123",
                    "message_id": "456",
                    "emoji": "thumbs_up"
                }
            })

            assert response["request_completed"] is True

        def test_update_reactions_list(self, processor, reaction_mock):
            """Test updating the reaction list"""
            result = processor._update_reactions_list(reaction_mock, "👍")
            assert len(result) == 1
            assert result[0].emoticon == "❤️"

            result = processor._update_reactions_list(reaction_mock, "🔥")
            assert len(result) == 2
            assert {r.emoticon for r in result} == {"👍", "❤️"}

            result = processor._update_reactions_list(None, "👍")
            result = processor._update_reactions_list(None, "👍")
            assert result == []

    class TestPinUnpin:
        """Tests for pin/unpin message methods"""

        @pytest.mark.asyncio
        async def test_pin_message_success(self, processor, telethon_client_mock):
            """Test successfully pinning a message"""
            telethon_client_mock.return_value = MagicMock()
            telethon_client_mock.get_entity.return_value = "entity"

            response = await processor.process_event({
                "event_type": "pin_message",
                "data": {
                    "conversation_id": "123",
                    "message_id": "456"
                }
            })

            assert response["request_completed"] is True
            telethon_client_mock.assert_called_once()
            processor.rate_limiter.limit_request.assert_called_with("pin_message", "123")

        @pytest.mark.asyncio
        async def test_pin_message_missing_required_fields(self, processor):
            """Test pinning a message with missing required fields"""
            # Missing conversation_id
            response = await processor.process_event({
                "event_type": "pin_message",
                "data": {"message_id": "456"}
            })
            assert response["request_completed"] is False

            # Missing message_id
            response = await processor.process_event({
                "event_type": "pin_message",
                "data": {"conversation_id": "123"}
            })
            assert response["request_completed"] is False

        @pytest.mark.asyncio
        async def test_unpin_message_success(self, processor, telethon_client_mock):
            """Test successfully unpinning a message"""
            telethon_client_mock.return_value = MagicMock()
            telethon_client_mock.get_entity.return_value = "entity"

            response = await processor.process_event({
                "event_type": "unpin_message",
                "data": {
                    "conversation_id": "123",
                    "message_id": "456"
                }
            })

            assert response["request_completed"] is True
            telethon_client_mock.assert_called_once()
            processor.rate_limiter.limit_request.assert_called_with("unpin_message", "123")

        @pytest.mark.asyncio
        async def test_unpin_message_missing_required_fields(self, processor):
            """Test unpinning a message with missing required fields"""
            # Missing conversation_id
            response = await processor.process_event({
                "event_type": "unpin_message",
                "data": {"message_id": "456"}
            })
            assert response["request_completed"] is False

            # Missing message_id (when not unpinning all)
            response = await processor.process_event({
                "event_type": "unpin_message",
                "data": {"conversation_id": "123"}
            })
            assert response["request_completed"] is False

    class TestHelperMethods:
        """Tests for helper methods"""

        @pytest.mark.asyncio
        async def test_get_entity_success(self, processor, telethon_client_mock):
            """Test successfully getting an entity"""
            telethon_client_mock.get_entity.return_value = "test_entity"

            assert await processor._get_entity("123") == "test_entity"
            telethon_client_mock.get_entity.assert_called_once_with("123")
