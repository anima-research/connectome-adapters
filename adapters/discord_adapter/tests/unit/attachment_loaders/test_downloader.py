import json
import logging
import os
import pytest
import shutil

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import core.utils.attachment_loading
from adapters.discord_adapter.adapter.attachment_loaders.downloader import Downloader

class TestDownloader:
    """Tests for the Discord Downloader class"""

    @pytest.fixture(scope="class", autouse=True)
    def ensure_test_directories(self):
        """Create necessary test directories before tests and clean up after"""
        os.makedirs("test_attachments", exist_ok=True)
        os.makedirs("test_attachments/document", exist_ok=True)

        yield

        if os.path.exists("test_attachments"):
            shutil.rmtree("test_attachments")

    @pytest.fixture
    def attachment_mock(self):
        """Create a mocked Discord message"""
        attachment = MagicMock()
        attachment.filename = "test.pdf"
        attachment.id = "xyz123"
        attachment.size = 12345
        attachment.save = AsyncMock()
        return attachment

    @pytest.fixture
    def discord_message_mock(self, attachment_mock):
        """Create a mocked Discord message with no attachments"""
        message = MagicMock()
        message.attachments = [attachment_mock]
        return message

    @pytest.fixture
    def rate_limiter_mock(self):
        """Create a mock rate limiter"""
        rate_limiter = AsyncMock()
        rate_limiter.limit_request = AsyncMock(return_value=None)
        rate_limiter.get_wait_time = AsyncMock(return_value=0)
        return rate_limiter

    @pytest.fixture
    def downloader(self, patch_config):
        """Create a Downloader with mocked dependencies"""
        return Downloader(patch_config)

    @pytest.mark.asyncio
    async def test_download_attachment_new_file(self, downloader, discord_message_mock):
        """Test downloading a new attachment"""
        with patch("os.path.exists", side_effect=[False, True]):  # File doesn't exist, then does after download
            with patch("core.utils.attachment_loading.create_attachment_dir"):
                with patch("core.utils.attachment_loading.save_metadata_file"):
                    with patch("builtins.open", mock_open(read_data=b"test file content")):
                        with patch.object(logging, "info") as mock_log:
                            result = await downloader.download_attachment(discord_message_mock)

                            assert len(result) == 1
                            assert result[0]["attachment_id"] == "xyz123"
                            assert result[0]["size"] == 12345

                            discord_message_mock.attachments[0].save.assert_called_once()

                            assert mock_log.called
                            assert "Downloaded" in mock_log.call_args_list[0][0][0]

    @pytest.mark.asyncio
    async def test_download_attachment_existing_file(self, downloader, discord_message_mock):
        """Test handling an existing attachment"""
        with patch("os.path.exists", return_value=True):  # File already exists
            with patch("core.utils.attachment_loading.save_metadata_file"):
                with patch("builtins.open", mock_open(read_data=b"test file content")):
                    with patch.object(logging, "info") as mock_log:
                        result = await downloader.download_attachment(discord_message_mock)

                        assert len(result) == 1
                        assert result[0]["attachment_id"] == "xyz123"
                        assert result[0]["size"] == 12345
                        assert mock_log.called
                        assert "Skipping download" in mock_log.call_args_list[0][0][0]

    @pytest.mark.asyncio
    async def test_download_attachment_no_attachments(self, downloader, discord_message_mock):
        """Test handling a message with no attachments"""
        discord_message_mock.attachments = []

        assert await downloader.download_attachment(discord_message_mock) == []
