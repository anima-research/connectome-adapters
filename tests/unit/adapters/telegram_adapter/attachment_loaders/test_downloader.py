import json
import os
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

import src.core.utils.attachment_loading
from src.adapters.telegram_adapter.attachment_loaders.downloader import Downloader

class TestDownloader:
    """Tests for the Downloader class"""

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
    def downloader(self, client_mock, rate_limiter_mock, telegram_config):
        """Create a Downloader with mocked dependencies"""
        downloader = Downloader(telegram_config, client_mock)
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

    @pytest.mark.asyncio
    async def test_download_file(self, downloader, mock_standard_file_message):
        """Test downloading a standard file"""
        metadata = {
            "attachment_id": "photo789",
            "attachment_type": "photo",
            "filename": "photo789.jpg",
            "size": 12345,
            "content_type": "image/jpeg",
            "content": None,
            "url": None,
            "created_at": datetime.now(),
            "processable": True
        }

        with patch.object(downloader, "_get_attachment_metadata", return_value=metadata):
            with patch("os.path.exists", return_value=False):  # File doesn't exist
                with patch("src.core.utils.attachment_loading.create_attachment_dir"):
                    with patch("magic.Magic") as mock_magic:
                        mock_magic_instance = mock_magic.return_value
                        mock_magic_instance.from_file.return_value = "image/jpeg"

                        with patch("src.core.utils.attachment_loading.save_metadata_file"):
                            result = await downloader.download_attachment(mock_standard_file_message)

                            assert result["attachment_id"] == "photo789"
                            assert result["processable"] == True
                            downloader.client.download_media.assert_called_once()
