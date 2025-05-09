import json
import os
import pytest
import shutil
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

import core.utils.attachment_loading
from adapters.telegram_adapter.adapter.attachment_loaders.downloader import Downloader

class TestDownloader:
    """Tests for the Downloader class"""

    @pytest.fixture(scope="class", autouse=True)
    def ensure_test_directories(self):
        """Create necessary test directories before tests and clean up after"""
        os.makedirs("test_attachments", exist_ok=True)
        os.makedirs("test_attachments/image", exist_ok=True)
        os.makedirs("test_attachments/document", exist_ok=True)

        yield

        if os.path.exists("test_attachments"):
            shutil.rmtree("test_attachments")

    @pytest.fixture
    def client_mock(self):
        """Create a mocked Telethon client"""
        client = AsyncMock()
        client.download_media = AsyncMock(return_value="downloaded_file_path")
        return client

    @pytest.fixture
    def rate_limiter_mock(self):
        """Create a mock rate limiter"""
        rate_limiter = AsyncMock()
        rate_limiter.limit_request = AsyncMock(return_value=None)
        rate_limiter.get_wait_time = AsyncMock(return_value=0)
        return rate_limiter

    @pytest.fixture
    def downloader(self, client_mock, rate_limiter_mock, patch_config):
        """Create a Downloader with mocked dependencies"""
        downloader = Downloader(patch_config, client_mock)
        downloader.rate_limiter = rate_limiter_mock
        return downloader

    @pytest.fixture
    def mock_standard_file_message(self):
        """Create a mock message with a photo attachment"""
        message = MagicMock()
        message.id = "123"
        photo = MagicMock()
        photo.id = "photo789"
        size = MagicMock()
        size.size = 12345
        photo.sizes = [size]
        message.photo = photo
        message.media = MagicMock()
        message.document = None
        return message

    @pytest.fixture
    def mock_large_file_message(self):
        """Create a mock message with a large file attachment"""
        message = MagicMock()
        message.id = "789"
        document = MagicMock()
        document.id = "large123"
        document.size = 60 * 1024 * 1024  # 60 MB, above threshold
        attr = MagicMock()
        attr.file_name = "large.mp4"
        document.attributes = [attr]
        message.document = document
        message.photo = None
        message.media = MagicMock()
        return message

    class TestDownloadAttachment:
        """Tests for the download_attachment method"""

        @pytest.mark.asyncio
        async def test_download_file(self, downloader, mock_standard_file_message):
            """Test downloading a standard file"""
            metadata = {
                "attachment_id": "photo789",
                "attachment_type": "photo",
                "file_extension": "jpg",
                "created_at": datetime.now(),
                "size": 12345,
                "processable": True,
                "content": None
            }
            file_path = "/fake/path/photo/photo789/photo789.jpg"

            with patch.object(downloader, "_get_attachment_metadata", return_value=metadata):
                with patch("os.path.join", return_value=file_path):
                    with patch("os.path.exists", return_value=False):  # File doesn't exist
                        with patch("core.utils.attachment_loading.create_attachment_dir"):
                            with patch.object(downloader, "_download_file") as mock_download:
                                with patch("core.utils.attachment_loading.save_metadata_file"):
                                    result = await downloader.download_attachment(mock_standard_file_message)

                                    assert result["attachment_id"] == "photo789"
                                    assert result["processable"] == True
                                    mock_download.assert_called_once()
