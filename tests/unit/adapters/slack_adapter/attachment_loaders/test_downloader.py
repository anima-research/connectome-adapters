import aiohttp
import json
import logging
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import src.core.utils.attachment_loading
from src.adapters.slack_adapter.attachment_loaders.downloader import Downloader

class TestDownloader:
    """Tests for the Slack Downloader class"""

    @pytest.fixture
    def small_file_mock(self):
        """Create a mocked small Slack file"""
        return {
            "id": "F123456",
            "name": "test.pdf",
            "size": 5000,
            "mimetype": "application/pdf",
            "url_private": "https://slack.com/files/test.pdf"
        }

    @pytest.fixture
    def large_file_mock(self):
        """Create a mocked large Slack file"""
        return {
            "id": "F789012",
            "name": "large.mp4",
            "size": 15 * 1024 * 1024,  # 15MB
            "mimetype": "video/mp4",
            "url_private": "https://slack.com/files/large.mp4"
        }

    @pytest.fixture
    def slack_message_with_files(self, small_file_mock, large_file_mock):
        """Create a mocked Slack message with files"""
        return {
            "files": [small_file_mock, large_file_mock],
            "ts": "1234567890.123456",
            "user": "U123456"
        }

    @pytest.fixture
    def slack_message_no_files(self):
        """Create a mocked Slack message with no files"""
        return {
            "text": "Hello world",
            "ts": "1234567890.123456",
            "user": "U123456"
        }

    @pytest.fixture
    def mock_client(self):
        """Create a mock Slack client"""
        client = AsyncMock()
        client.token = "xoxb-test-token-123"
        client.files_info.return_value = {
            "file": {
                "id": "F123456",
                "url_private": "https://slack.com/files/test.pdf"
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
    def downloader(self, slack_config, mock_client, rate_limiter_mock):
        """Create a Downloader with mocked dependencies"""
        downloader = Downloader(slack_config, mock_client)
        downloader.rate_limiter = rate_limiter_mock
        return downloader

    @pytest.mark.asyncio
    async def test_download_no_attachments(self, downloader, slack_message_no_files):
        """Test handling a message with no files"""
        assert await downloader.download_attachments(slack_message_no_files) == []

    @pytest.mark.asyncio
    async def test_download_attachments_with_empty_files(self, downloader):
        """Test handling a message with empty files list"""
        assert await downloader.download_attachments({"files": []}) == []

    @pytest.mark.asyncio
    async def test_download_new_file(self, downloader, slack_message_with_files):
        """Test downloading a new small file"""
        with patch.object(downloader, "_download_file", AsyncMock()) as mock_download:
            with patch("os.path.exists", return_value=False):  # File doesn't exist
                with patch("src.core.utils.attachment_loading.create_attachment_dir"):
                    with patch("src.core.utils.attachment_loading.save_metadata_file"):
                        with patch("builtins.open", mock_open(read_data=b"test file content")):
                            with patch.object(logging, "info"):
                                message = {"files": [slack_message_with_files["files"][0]]}
                                result = await downloader.download_attachments(message)

                                assert len(result) == 1
                                assert result[0]["attachment_id"] == "F123456"
                                assert result[0]["size"] == 5000

                                mock_download.assert_called_once()

    @pytest.mark.asyncio
    async def test_download_existing_file(self, downloader, slack_message_with_files):
        """Test handling an existing completed attachment"""
        with patch("os.path.exists", return_value=True):  # File already exists
            with patch("os.path.getsize", return_value=5000):
                with patch("src.core.utils.attachment_loading.save_metadata_file"):
                    with patch("builtins.open", mock_open(read_data=b"test file content")):
                        with patch.object(logging, "info") as mock_log:
                            message = {"files": [slack_message_with_files["files"][0]]}
                            result = await downloader.download_attachments(message)

                            assert len(result) == 1
                            assert result[0]["attachment_id"] == "F123456"
                            assert result[0]["size"] == 5000

                            assert not downloader.client.files_info.called
                            assert mock_log.called
                            assert "Skipping download" in mock_log.call_args[0][0]

    @pytest.mark.asyncio
    async def test_multiple_file_types(self, downloader):
        """Test handling different file types"""
        files = [
            {
                "id": "F123456",
                "name": "document.pdf",
                "size": 5000,
                "mimetype": "application/pdf",
                "url_private": "https://slack.com/files/document.pdf"
            },
            {
                "id": "F789012",
                "name": "image.jpg",
                "size": 8000,
                "mimetype": "image/jpeg",
                "url_private": "https://slack.com/files/image.jpg"
            }
        ]
        message = {"files": files}

        with patch("os.path.exists", return_value=False):
            with patch.object(downloader, "_download_file", AsyncMock()):
                with patch("src.core.utils.attachment_loading.create_attachment_dir"):
                    with patch("src.core.utils.attachment_loading.save_metadata_file"):
                        with patch("builtins.open", mock_open(read_data=b"")):
                            result = await downloader.download_attachments(message)

                            assert len(result) == 2
                            assert result[0]["attachment_type"] == "document"
                            assert result[0]["filename"] == f"{files[0]['id']}.pdf"
                            assert result[1]["attachment_type"] == "image"
                            assert result[1]["filename"] == f"{files[1]['id']}.jpg"
