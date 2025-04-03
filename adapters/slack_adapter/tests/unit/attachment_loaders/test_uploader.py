import logging
import os
import pytest

from unittest.mock import patch, MagicMock, AsyncMock
from adapters.slack_adapter.adapter.attachment_loaders.uploader import Uploader

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
    def uploader(self, patch_config, mock_client, rate_limiter_mock):
        """Create an Uploader with mocked dependencies"""
        uploader = Uploader(patch_config, mock_client)
        uploader.rate_limiter = rate_limiter_mock
        return uploader

    @pytest.fixture
    def sample_attachment(self):
        """Create sample document attachment info"""
        return [
            {
                "attachment_type": "document",
                "file_path": "/test/path/document123.pdf",
                "size": 1000
            }
        ]

    @pytest.mark.asyncio
    async def test_file_not_found(self, uploader, sample_attachment):
        """Test handling missing file"""
        with patch("os.path.exists", return_value=False):
            with patch.object(logging, "error") as mock_log:
                await uploader.upload_attachments("T123/C456", sample_attachment)

                assert mock_log.called
                assert "File not found" in mock_log.call_args[0][0]
                assert not uploader.client.files_upload_v2.called

    @pytest.mark.asyncio
    async def test_file_too_large(self, uploader):
        """Test handling file that exceeds size limit"""
        oversized_attachment = [{
            "attachment_type": "video",
            "file_path": "/test/path/huge123.mp4",
            "size": 51 * 1024 * 1024  # 51MB, above 50MB limit
        }]

        with patch("os.path.exists", return_value=True):
            with patch.object(logging, "error") as mock_log:
                await uploader.upload_attachments("T123/C456", oversized_attachment)

                assert mock_log.called
                assert "exceeds Slack's size limit" in mock_log.call_args[0][0]
                assert not uploader.client.files_upload_v2.called

    @pytest.mark.asyncio
    async def test_upload_file_success(self, uploader, sample_attachment):
        """Test successful file upload"""
        with patch("os.path.exists", return_value=True):
            with patch("adapters.slack_adapter.adapter.attachment_loaders.uploader.move_attachment") as mock_move:
                with patch("adapters.slack_adapter.adapter.attachment_loaders.uploader.create_attachment_dir") as mock_create_dir:
                    with patch("adapters.slack_adapter.adapter.attachment_loaders.uploader.delete_empty_directory") as mock_delete_dir:
                        await uploader.upload_attachments("T123/C456", sample_attachment)

                        uploader.client.files_upload_v2.assert_called_once_with(
                            file="/test/path/document123.pdf",
                            channel="C456"
                        )
                        assert mock_create_dir.called
                        assert mock_move.called
                        assert mock_delete_dir.called

    @pytest.mark.asyncio
    async def test_upload_file_api_error(self, uploader, sample_attachment):
        """Test handling API errors"""
        uploader.client.files_upload_v2.return_value = {
            "ok": False,
            "error": "invalid_auth"
        }

        with patch("os.path.exists", return_value=True):
            with patch.object(logging, "error"):
                await uploader.upload_attachments("T123/C456", sample_attachment)
                assert uploader.client.files_upload_v2.called

    @pytest.mark.asyncio
    async def test_upload_file_exception(self, uploader, sample_attachment):
        """Test handling exceptions during upload"""
        uploader.client.files_upload_v2.side_effect = Exception("Network error")

        with patch("os.path.exists", return_value=True):
            with patch.object(logging, "error") as mock_log:
                await uploader.upload_attachments("T123/C456", sample_attachment)

                assert mock_log.called
                assert "Error uploading file" in mock_log.call_args[0][0]

    @pytest.mark.asyncio
    async def test_multiple_attachments(self, uploader):
        """Test uploading multiple attachments"""
        multiple_attachments = [
            {
                "attachment_type": "document",
                "file_path": "/test/path/doc1.pdf",
                "size": 1000
            },
            {
                "attachment_type": "image",
                "file_path": "/test/path/img1.jpg",
                "size": 2000
            }
        ]

        with patch("os.path.exists", return_value=True):
            with patch("adapters.slack_adapter.adapter.attachment_loaders.uploader.move_attachment"):
                with patch("adapters.slack_adapter.adapter.attachment_loaders.uploader.create_attachment_dir"):
                    with patch("adapters.slack_adapter.adapter.attachment_loaders.uploader.delete_empty_directory"):
                        await uploader.upload_attachments("T123/C456", multiple_attachments)

                        assert uploader.client.files_upload_v2.call_count == 2
                        assert uploader.rate_limiter.limit_request.call_count == 2
