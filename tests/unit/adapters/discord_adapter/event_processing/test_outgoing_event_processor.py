import discord
import os
import pytest

from unittest.mock import AsyncMock, MagicMock, patch, call
from src.adapters.discord_adapter.event_processing.attachment_loaders.uploader import Uploader
from src.adapters.discord_adapter.event_processing.outgoing_event_processor import OutgoingEventProcessor

class TestOutgoingEventProcessor:
    """Tests for the Discord OutgoingEventProcessor class"""

    @pytest.fixture
    def discord_client_mock(self):
        """Create a mocked Discord client"""
        client = AsyncMock()
        client.user = MagicMock()
        channel_mock = AsyncMock()
        channel_mock.send = AsyncMock()
        channel_mock.fetch_message = AsyncMock()
        client.get_channel = MagicMock(return_value=channel_mock)
        client.fetch_channel = AsyncMock(return_value=channel_mock)
        return client

    @pytest.fixture
    def conversation_manager_mock(self):
        """Create a mocked conversation manager"""
        manager = AsyncMock()
        manager.get_conversation = MagicMock()
        return manager

    @pytest.fixture
    def channel_mock(self):
        """Create a mocked Discord channel"""
        channel = AsyncMock()
        channel.send = AsyncMock(return_value=MagicMock(id=999))
        message_mock = AsyncMock()
        message_mock.edit = AsyncMock()
        message_mock.delete = AsyncMock()
        message_mock.add_reaction = AsyncMock()
        message_mock.remove_reaction = AsyncMock()
        channel.fetch_message = AsyncMock(return_value=message_mock)
        return channel

    @pytest.fixture
    def uploader_mock(self):
        """Create a mocked uploader"""
        uploader = MagicMock()
        uploader.upload_attachment = MagicMock(return_value=[[], []])
        uploader.clean_up_uploaded_files = MagicMock()
        return uploader

    @pytest.fixture
    def processor(self,
                  discord_config,
                  discord_client_mock,
                  conversation_manager_mock,
                  channel_mock,
                  rate_limiter_mock,
                  uploader_mock):
        """Create a DiscordOutgoingEventProcessor with mocked dependencies"""
        with patch.object(Uploader, "upload_attachment", return_value=[[], []]):
            processor = OutgoingEventProcessor(discord_config, discord_client_mock, conversation_manager_mock)
            processor._get_channel = AsyncMock(return_value=channel_mock)
            processor.rate_limiter = rate_limiter_mock
            processor.uploader = uploader_mock
            return processor

    class TestSendMessage:
        """Tests for the send_message method"""

        @pytest.mark.asyncio
        async def test_send_message_success(self, processor, channel_mock):
            """Test sending a simple message successfully"""
            response = await processor.process_event({
                "event_type": "send_message",
                "data": {
                    "conversation_id": "123456789",
                    "text": "Hello, world!"
                }
            })
            assert response["request_completed"] is True

            processor.rate_limiter.limit_request.assert_called_once_with(
                "message", "123456789"
            )
            channel_mock.send.assert_called_once_with("Hello, world!")

        @pytest.mark.asyncio
        async def test_send_message_long_text(self, processor, channel_mock):
            """Test sending a message with text longer than max length"""
            event_data = {
                "event_type": "send_message",
                "data": {
                    "conversation_id": "123456789",
                    "text": "This is a sentence. " * 100  # Well over Discord's limit
                }
            }

            with patch.object(processor, "_split_long_message", return_value=["Part 1", "Part 2"]):
                response = await processor.process_event(event_data)
                assert response["request_completed"] is True

            assert channel_mock.send.call_count == 2
            channel_mock.send.assert_has_calls([call("Part 1"), call("Part 2")])

        @pytest.mark.asyncio
        async def test_send_message_with_attachments(self, processor, channel_mock):
            """Test sending a message with attachments"""
            attachments = [
                {
                    "file_name": "file1.txt",
                    "content": "test content"
                }
            ]
            event_data = {
                "event_type": "send_message",
                "data": {
                    "conversation_id": "123456789",
                    "text": "Message with attachments",
                    "attachments": attachments
                }
            }

            with patch('os.remove'):
                response = await processor.process_event(event_data)
                assert response["request_completed"] is True
                assert channel_mock.send.call_count == 2

                processor.uploader.upload_attachment.assert_called_once()
                processor.uploader.clean_up_uploaded_files.assert_called_once()

        @pytest.mark.asyncio
        async def test_send_message_with_many_attachments(self,
                                                          processor,
                                                          channel_mock,
                                                          uploader_mock):
            """Test sending a message with many attachments that need to be chunked"""
            attachments = [
                {
                    "file_name": f"file{i}.txt",
                    "content": "test content"
                } for i in range(2)
            ]
            event_data = {
                "event_type": "send_message",
                "data": {
                    "conversation_id": "123456789",
                    "text": "Message with many attachments",
                    "attachments": attachments
                }
            }

            # discord_config sets attachment limit to 1, so even 2 files will be chunked
            chunk1_files = [MagicMock(), MagicMock()]
            chunk2_files = [MagicMock(), MagicMock()]

            uploader_mock.upload_attachment.side_effect = [
                chunk1_files, chunk2_files
            ]

            with patch('os.remove'):
                response = await processor.process_event(event_data)
                assert response["request_completed"] is True
                assert channel_mock.send.call_count == 3
                assert uploader_mock.upload_attachment.call_count == 2
                uploader_mock.clean_up_uploaded_files.assert_called_once()

        @pytest.mark.asyncio
        async def test_send_message_channel_not_found(self, processor):
            """Test sending a message when channel isn't found"""
            event_data = {
                "event_type": "send_message",
                "data": {
                    "conversation_id": "999999",
                    "text": "Hello, world!"
                }
            }
            processor._get_channel.side_effect = Exception("Channel not found")

            response = await processor.process_event(event_data)
            assert response["request_completed"] is False

    class TestEditMessage:
        """Tests for the edit_message method"""

        @pytest.mark.asyncio
        async def test_edit_message_success(self, processor, channel_mock):
            """Test successfully editing a message"""
            event_data = {
                "event_type": "edit_message",
                "data": {
                    "conversation_id": "123456789",
                    "message_id": "987654321",
                    "text": "Updated text"
                }
            }

            response = await processor.process_event(event_data)
            assert response["request_completed"] is True

            processor.rate_limiter.limit_request.assert_called_once_with(
                "edit_message", "123456789"
            )
            channel_mock.fetch_message.assert_called_once_with(987654321)
            message = channel_mock.fetch_message.return_value
            message.edit.assert_called_once_with(content="Updated text")

        @pytest.mark.asyncio
        async def test_edit_message_not_found(self, processor, channel_mock):
            """Test editing a message that doesn't exist"""
            event_data = {
                "event_type": "edit_message",
                "data": {
                    "conversation_id": "123456789",
                    "message_id": "987654321",
                    "text": "Updated text"
                }
            }
            channel_mock.fetch_message.side_effect = discord.NotFound(MagicMock(), "Message not found")

            response = await processor.process_event(event_data)
            assert response["request_completed"] is False

    class TestDeleteMessage:
        """Tests for the delete_message method"""

        @pytest.mark.asyncio
        async def test_delete_message_success(self, processor, channel_mock):
            """Test successfully deleting a message"""
            event_data = {
                "event_type": "delete_message",
                "data": {
                    "conversation_id": "123456789",
                    "message_id": "987654321"
                }
            }

            response = await processor.process_event(event_data)
            assert response["request_completed"] is True
            processor.rate_limiter.limit_request.assert_called_once_with(
                "delete_message", "123456789"
            )
            channel_mock.fetch_message.assert_called_once_with(987654321)
            message = channel_mock.fetch_message.return_value
            message.delete.assert_called_once()

        @pytest.mark.asyncio
        async def test_delete_message_not_found(self, processor, channel_mock):
            """Test deleting a message that doesn't exist"""
            event_data = {
                "event_type": "delete_message",
                "data": {
                    "conversation_id": "123456789",
                    "message_id": "987654321"
                }
            }
            channel_mock.fetch_message.side_effect = discord.NotFound(MagicMock(), "Message not found")

            response = await processor.process_event(event_data)
            assert response["request_completed"] is False

    class TestReactions:
        """Tests for the reaction-related methods"""

        @pytest.mark.asyncio
        async def test_add_reaction_success(self, processor, channel_mock):
            """Test successfully adding a reaction"""
            event_data = {
                "event_type": "add_reaction",
                "data": {
                    "conversation_id": "123456789",
                    "message_id": "987654321",
                    "emoji": "thumbs_up"
                }
            }

            response = await processor.process_event(event_data)
            assert response["request_completed"] is True
            processor.rate_limiter.limit_request.assert_called_once_with(
                "add_reaction", "123456789"
            )
            channel_mock.fetch_message.assert_called_once_with(987654321)
            message = channel_mock.fetch_message.return_value
            message.add_reaction.assert_called_once_with("👍")

        @pytest.mark.asyncio
        async def test_add_reaction_message_not_found(self, processor, channel_mock):
            """Test adding a reaction to a message that doesn't exist"""
            event_data = {
                "event_type": "add_reaction",
                "data": {
                    "conversation_id": "123456789",
                    "message_id": "987654321",
                    "emoji": "+1"
                }
            }
            channel_mock.fetch_message.side_effect = discord.NotFound(MagicMock(), "Message not found")

            response = await processor.process_event(event_data)
            assert response["request_completed"] is False

        @pytest.mark.asyncio
        async def test_remove_reaction_success(self, processor, channel_mock, discord_client_mock):
            """Test successfully removing a reaction"""
            event_data = {
                "event_type": "remove_reaction",
                "data": {
                    "conversation_id": "123456789",
                    "message_id": "987654321",
                    "emoji": "thumbs_up"
                }
            }

            response = await processor.process_event(event_data)
            assert response["request_completed"] is True
            processor.rate_limiter.limit_request.assert_called_once_with(
                "remove_reaction", "123456789"
            )
            channel_mock.fetch_message.assert_called_once_with(987654321)
            message = channel_mock.fetch_message.return_value
            message.remove_reaction.assert_called_once_with("👍", discord_client_mock.user)

    class TestPinStatusUpdate:
        """Tests for pin and unpin message methods"""

        @pytest.mark.asyncio
        async def test_pin_message_success(self, processor, channel_mock):
            """Test successfully pinning a message"""
            response = await processor.process_event({
                "event_type": "pin_message",
                "data": {
                    "conversation_id": "123456789",
                    "message_id": "987654321"
                }
            })
            assert response["request_completed"] is True

            processor.rate_limiter.limit_request.assert_called_once_with(
                "pin_message", "123456789"
            )
            channel_mock.fetch_message.assert_called_once_with(987654321)
            message = channel_mock.fetch_message.return_value
            message.pin.assert_called_once()

        @pytest.mark.asyncio
        async def test_pin_message_not_found(self, processor, channel_mock):
            """Test pinning a message that doesn't exist"""
            channel_mock.fetch_message.side_effect = discord.NotFound(MagicMock(), "Message not found")

            response = await processor.process_event({
                "event_type": "pin_message",
                "data": {
                    "conversation_id": "123456789",
                    "message_id": "987654321"
                }
            })
            assert response["request_completed"] is False

        @pytest.mark.asyncio
        async def test_unpin_message_success(self, processor, channel_mock):
            """Test successfully unpinning a message"""
            response = await processor.process_event({
                "event_type": "unpin_message",
                "data": {
                    "conversation_id": "123456789",
                    "message_id": "987654321"
                }
            })
            assert response["request_completed"] is True

            processor.rate_limiter.limit_request.assert_called_once_with(
                "unpin_message", "123456789"
            )
            channel_mock.fetch_message.assert_called_once_with(987654321)
            message = channel_mock.fetch_message.return_value
            message.unpin.assert_called_once()

        @pytest.mark.asyncio
        async def test_unpin_message_not_found(self, processor, channel_mock):
            """Test unpinning a message that doesn't exist"""
            channel_mock.fetch_message.side_effect = discord.NotFound(MagicMock(), "Message not found")
            response = await processor.process_event({
                "event_type": "unpin_message",
                "data": {
                    "conversation_id": "123456789",
                    "message_id": "987654321"
                }
            })
            assert response["request_completed"] is False
