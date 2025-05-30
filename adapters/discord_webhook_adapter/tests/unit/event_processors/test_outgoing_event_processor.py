import aiohttp
import discord
import json
import os
import pytest
import shutil
from unittest.mock import AsyncMock, MagicMock, patch, call

from adapters.discord_webhook_adapter.adapter.event_processors.outgoing_event_processor import OutgoingEventProcessor
from core.events.processors.base_outgoing_event_processor import OutgoingEventType

class TestOutgoingEventProcessor:
    """Tests for the Discord Webhook OutgoingEventProcessor class"""

    @pytest.fixture(scope="class", autouse=True)
    def ensure_test_directories(self):
        """Create necessary test directories before tests and clean up after"""
        os.makedirs("test_attachments", exist_ok=True)
        os.makedirs("test_attachments/document", exist_ok=True)

        with open("test_attachments/document/test.txt", "w") as f:
            f.write("Test content")

        yield

        if os.path.exists("test_attachments"):
            shutil.rmtree("test_attachments")

    @pytest.fixture
    def client_mock(self):
        """Create a mocked Discord webhook client"""
        client = MagicMock()
        client.session = AsyncMock()

        response_mock = AsyncMock()
        response_mock.status = 200
        response_mock.json = AsyncMock(return_value={"id": "111222333"})
        client.session.post = AsyncMock(return_value=response_mock)
        client.session.patch = AsyncMock(return_value=response_mock)
        client.session.delete = AsyncMock(return_value=response_mock)

        client.get_or_create_webhook = AsyncMock(return_value={
            "url": "https://discord.com/api/webhooks/123456789/token",
            "name": "Test Bot"
        })

        return client

    @pytest.fixture
    def conversation_manager_mock(self):
        """Create a mocked conversation manager"""
        manager = MagicMock()
        manager.add_to_conversation = MagicMock()
        manager.delete_from_conversation = MagicMock()
        return manager

    @pytest.fixture
    def rate_limiter_mock(self):
        """Create a mocked rate limiter"""
        rate_limiter = AsyncMock()
        rate_limiter.limit_request = AsyncMock()
        return rate_limiter

    @pytest.fixture
    def uploader_mock(self):
        """Create a mocked uploader"""
        uploader = MagicMock()
        uploader.upload_attachment = MagicMock()
        uploader.clean_up_uploaded_files = MagicMock()
        return uploader

    @pytest.fixture
    def processor(self,
                  patch_config,
                  client_mock,
                  conversation_manager_mock,
                  rate_limiter_mock,
                  uploader_mock):
        """Create an OutgoingEventProcessor with mocked dependencies"""
        processor = OutgoingEventProcessor(
            patch_config, client_mock, conversation_manager_mock
        )
        processor.rate_limiter = rate_limiter_mock
        processor.uploader = uploader_mock
        processor.session = client_mock.session
        return processor

    class TestSendMessage:
        """Tests for the send_message method"""

        @pytest.mark.asyncio
        async def test_send_message_success(self, processor, client_mock):
            """Test sending a simple message successfully"""
            event_data = {
                "event_type": "send_message",
                "data": {
                    "conversation_id": "987654321/123456789",
                    "text": "Hello, world!"
                }
            }

            response_mock = MagicMock()
            response_mock.status = 200
            response_mock.json = AsyncMock(return_value={"id": "111222333"})
            processor.session.post = AsyncMock(return_value=response_mock)

            result = await processor.process_event(event_data)
            assert result["request_completed"] is True

            client_mock.get_or_create_webhook.assert_called_with("987654321/123456789")
            processor.rate_limiter.limit_request.assert_called_with(
                "message", "https://discord.com/api/webhooks/123456789/token"
            )
            processor.session.post.assert_called_with(
                "https://discord.com/api/webhooks/123456789/token?wait=true",
                json={"content": "Hello, world!", "username": "Test Bot"}
            )
            processor.conversation_manager.add_to_conversation.assert_called()

        @pytest.mark.asyncio
        async def test_send_message_with_custom_name(self, processor):
            """Test sending a message with a custom name"""
            event_data = {
                "event_type": "send_message",
                "data": {
                    "conversation_id": "987654321/123456789",
                    "text": "Hello with custom name",
                    "custom_name": "Custom Bot Name"
                }
            }

            response_mock = MagicMock()
            response_mock.status = 200
            response_mock.json = AsyncMock(return_value={"id": "111222333"})
            processor.session.post = AsyncMock(return_value=response_mock)

            result = await processor.process_event(event_data)
            assert result["request_completed"] is True
            processor.session.post.assert_called_with(
                "https://discord.com/api/webhooks/123456789/token?wait=true",
                json={"content": "Hello with custom name", "username": "Custom Bot Name"}
            )

        @pytest.mark.asyncio
        async def test_send_message_long_text(self, processor):
            """Test sending a message with text longer than max length"""
            event_data = {
                "event_type": "send_message",
                "data": {
                    "conversation_id": "987654321/123456789",
                    "text": "This is a sentence. " * 10
                }
            }

            response_mock = MagicMock()
            response_mock.status = 200
            response_mock.json = AsyncMock(return_value={"id": "111222333"})
            processor.session.post = AsyncMock(return_value=response_mock)

            with patch.object(processor, "_split_long_message", return_value=["Part 1", "Part 2"]):
                result = await processor.process_event(event_data)
                assert result["request_completed"] is True
            assert processor.session.post.call_count == 2

            processor.session.post.assert_any_call(
                "https://discord.com/api/webhooks/123456789/token?wait=true",
                json={"content": "Part 1", "username": "Test Bot"}
            )
            processor.session.post.assert_any_call(
                "https://discord.com/api/webhooks/123456789/token?wait=true",
                json={"content": "Part 2", "username": "Test Bot"}
            )

        @pytest.mark.asyncio
        async def test_send_message_with_attachments(self, processor, uploader_mock):
            """Test sending a message with attachments"""
            event_data = {
                "event_type": "send_message",
                "data": {
                    "conversation_id": "987654321/123456789",
                    "text": "Message with attachments",
                    "attachments": [
                        {
                            "file_name": "test.txt",
                            "content": "dGVzdAo="
                        }
                    ]
                }
            }

            text_response_mock = MagicMock()
            text_response_mock.status = 200
            text_response_mock.json = AsyncMock(return_value={"id": "111222333"})

            attachment_response_mock = MagicMock()
            attachment_response_mock.status = 200
            attachment_response_mock.json = AsyncMock(return_value={"id": "444555666"})

            uploader_mock.upload_attachment.return_value = ["tmp_uploads/test.txt"]
            processor.session.post = AsyncMock(side_effect=[text_response_mock, attachment_response_mock])

            with patch('aiohttp.FormData') as form_data_mock:
                form_instance = MagicMock()
                form_data_mock.return_value = form_instance

                result = await processor.process_event(event_data)
                assert result["request_completed"] is True
                uploader_mock.upload_attachment.assert_called_once()

                assert form_data_mock.called
                uploader_mock.clean_up_uploaded_files.assert_called_once()

    class TestEditMessage:
        """Tests for the edit_message method"""

        @pytest.mark.asyncio
        async def test_edit_message_success(self, processor, client_mock):
            """Test successfully editing a message"""
            event_data = {
                "event_type": "edit_message",
                "data": {
                    "conversation_id": "987654321/123456789",
                    "message_id": "111222333",
                    "text": "Updated text"
                }
            }

            response_mock = MagicMock()
            response_mock.status = 200
            response_mock.json = AsyncMock(return_value={"id": "111222333"})
            processor.session.patch = AsyncMock(return_value=response_mock)

            result = await processor.process_event(event_data)
            assert result["request_completed"] is True

            processor.rate_limiter.limit_request.assert_called_with(
                "edit_message", "https://discord.com/api/webhooks/123456789/token"
            )
            processor.session.patch.assert_called_with(
                "https://discord.com/api/webhooks/123456789/token/messages/111222333",
                json={"content": "Updated text"}
            )

    class TestDeleteMessage:
        """Tests for the delete_message method"""

        @pytest.mark.asyncio
        async def test_delete_message_success(self, processor):
            """Test successfully deleting a message"""
            event_data = {
                "event_type": "delete_message",
                "data": {
                    "conversation_id": "987654321/123456789",
                    "message_id": "111222333"
                }
            }

            response_mock = MagicMock()
            response_mock.status = 204  # No content, success
            response_mock.text = AsyncMock(return_value="")
            processor.session.delete = AsyncMock(return_value=response_mock)

            result = await processor.process_event(event_data)
            assert result["request_completed"] is True

            processor.rate_limiter.limit_request.assert_called_with(
                "delete_message", "https://discord.com/api/webhooks/123456789/token"
            )
            processor.session.delete.assert_called_with(
                "https://discord.com/api/webhooks/123456789/token/messages/111222333"
            )
            processor.conversation_manager.delete_from_conversation.assert_called_once()

    class TestUtilityMethods:
        """Tests for utility methods"""

        @pytest.mark.asyncio
        async def test_get_webhook_info(self, processor, client_mock):
            """Test getting webhook info"""
            conversation_id = "987654321/123456789"
            webhook_info = await processor._get_webhook_info(conversation_id)

            client_mock.get_or_create_webhook.assert_called_with(conversation_id)
            assert webhook_info is not client_mock.get_or_create_webhook.return_value
            assert webhook_info == client_mock.get_or_create_webhook.return_value

        @pytest.mark.asyncio
        async def test_check_api_response_success(self, processor):
            """Test checking a successful API response"""
            response = MagicMock()
            response.status = 200

            await processor._check_api_response(response)

        @pytest.mark.asyncio
        async def test_check_api_response_error(self, processor):
            """Test checking an error API response"""
            response = MagicMock()
            response.status = 400
            response.text = AsyncMock(return_value="Bad Request")

            with pytest.raises(Exception, match="Error processing webhook message"):
                await processor._check_api_response(response)
