import logging
import os
import pytest

from unittest.mock import patch, MagicMock, AsyncMock
from src.adapters.slack_adapter.attachment_loaders.uploader import Uploader
from src.core.events.models.outgoing_events import OutgoingAttachmentInfo, SendMessageData

class TestUploader:
    """Tests for the Slack Uploader class"""

    @pytest.fixture
    def mock_client(self):
        """Create a mock Slack client"""
        client = AsyncMock()
        client.files_upload_v2.return_value = {
            "ok": True,
            "file": {
                "id": "F123456789"
            }
        }
        return client

    @pytest.fixture
    def rate_limiter_mock(self):
        """Create a mock rate limiter"""
        rate_limiter = AsyncMock()
        rate_limiter.limit_request = AsyncMock(return_value=None)
        rate_limiter.get_wait_time = AsyncMock(return_value=0)
        return rate_limiter

    @pytest.fixture
    def uploader(self, slack_config, mock_client, rate_limiter_mock):
        """Create an Uploader with mocked dependencies"""
        uploader = Uploader(slack_config, mock_client)
        uploader.rate_limiter = rate_limiter_mock
        return uploader

    @pytest.fixture
    def sample_send_message_data(self):
        """Create sample send message data"""
        return SendMessageData(
            conversation_id="T123/C456",
            text="Test message",
            attachments=[
                OutgoingAttachmentInfo(
                    file_name="test.txt",
                    content="dGVzdAo="
                )
            ]
        )

    @pytest.mark.asyncio
    async def test_upload_file_success(self, uploader, sample_send_message_data):
        """Test successful file upload"""
        with patch("os.path.exists", return_value=True):
            with patch("src.adapters.slack_adapter.attachment_loaders.uploader.move_attachment") as mock_move:
                with patch("src.adapters.slack_adapter.attachment_loaders.uploader.create_attachment_dir") as mock_create_dir:
                    await uploader.upload_attachments(sample_send_message_data)

                    uploader.client.files_upload_v2.assert_called_once_with(
                        file="test_attachments/tmp_uploads/test.txt",
                        channel="C456"
                    )
                    assert mock_create_dir.called
                    assert mock_move.called

    @pytest.mark.asyncio
    async def test_upload_file_api_error(self, uploader, sample_send_message_data):
        """Test handling API errors"""
        uploader.client.files_upload_v2.return_value = {
            "ok": False,
            "error": "invalid_auth"
        }

        with patch("os.path.exists", return_value=True):
            with patch.object(logging, "error"):
                await uploader.upload_attachments(sample_send_message_data)
                assert uploader.client.files_upload_v2.called

    @pytest.mark.asyncio
    async def test_upload_file_exception(self, uploader, sample_send_message_data):
        """Test handling exceptions during upload"""
        uploader.client.files_upload_v2.side_effect = Exception("Network error")

        with patch("os.path.exists", return_value=True):
            with patch.object(logging, "error") as mock_log:
                await uploader.upload_attachments(sample_send_message_data)

                assert mock_log.called
                assert "Error uploading file" in mock_log.call_args[0][0]

    @pytest.mark.asyncio
    async def test_multiple_attachments(self, uploader, sample_send_message_data):
        """Test uploading multiple attachments"""
        sample_send_message_data.attachments = [
            OutgoingAttachmentInfo(
                file_name="doc1.txt",
                content="dGVzdAo="
            ),
            OutgoingAttachmentInfo(
                file_name="doc2.txt",
                content="dGVzdAo="
            )
        ]

        with patch("os.path.exists", return_value=True):
            with patch("src.adapters.slack_adapter.attachment_loaders.uploader.move_attachment"):
                with patch("src.adapters.slack_adapter.attachment_loaders.uploader.create_attachment_dir"):
                    await uploader.upload_attachments(sample_send_message_data)

                    assert uploader.client.files_upload_v2.call_count == 2
                    assert uploader.rate_limiter.limit_request.call_count == 2
