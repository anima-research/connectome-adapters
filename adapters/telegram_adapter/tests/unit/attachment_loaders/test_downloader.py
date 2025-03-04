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
        async def test_download_standard_file(self, downloader, mock_standard_file_message):
            """Test downloading a standard file"""
            metadata = {
                "attachment_id": "photo789",
                "attachment_type": "photo",
                "file_extension": "jpg",
                "created_at": datetime.now(),
                "size": 12345
            }
            file_path = "/fake/path/photo/photo789/photo789.jpg"

            with patch.object(downloader, "_get_attachment_metadata", return_value=metadata):
                with patch("os.path.join", return_value=file_path):
                    with patch("os.path.exists", return_value=False):  # File doesn't exist
                        with patch("core.utils.attachment_loading.create_attachment_dir"):
                            with patch.object(downloader, "_download_standard_file") as mock_download:
                                with patch("core.utils.attachment_loading.save_metadata_file"):
                                    result = await downloader.download_attachment(
                                        mock_standard_file_message, download_required=True
                                    )

                                    assert result["attachment_id"] == "photo789"
                                    mock_download.assert_called_once_with(mock_standard_file_message, file_path)

        @pytest.mark.asyncio
        async def test_download_large_file(self, downloader, mock_large_file_message):
            """Test downloading a large file"""
            metadata = {
                "attachment_id": "large123",
                "attachment_type": "video",
                "file_extension": "mp4",
                "created_at": datetime.now(),
                "size": 60 * 1024 * 1024
            }
            file_path = "/fake/path/video/large123/large123.mp4"

            with patch.object(downloader, "_get_attachment_metadata", return_value=metadata):
                with patch("os.path.join", return_value=file_path):
                    with patch("os.path.exists", return_value=False):  # File doesn't exist
                        with patch("core.utils.attachment_loading.create_attachment_dir"):
                            with patch.object(downloader, "_download_large_file") as mock_download:
                                with patch("core.utils.attachment_loading.save_metadata_file"):
                                    result = await downloader.download_attachment(
                                        mock_large_file_message, download_required=True
                                    )

                                    assert result["attachment_id"] == "large123"
                                    mock_download.assert_called_once_with(mock_large_file_message, file_path)

        @pytest.mark.asyncio
        async def test_download_error_handling(self, downloader, mock_standard_file_message):
            """Test error handling during download"""
            metadata = {
                "attachment_id": "photo789",
                "attachment_type": "photo",
                "file_extension": "jpg",
                "created_at": datetime.now(),
                "size": 12345
            }
            file_path = "/fake/path/photo/photo789/photo789.jpg"

            with patch.object(downloader, "_get_attachment_metadata", return_value=metadata):
                with patch("os.path.join", return_value=file_path):
                    with patch("os.path.exists", return_value=False):  # File doesn't exist
                        with patch("core.utils.attachment_loading.create_attachment_dir"):
                            with patch.object(downloader, "_download_standard_file",
                                              side_effect=Exception("Test download error")) as mock_download:
                                with patch("core.utils.attachment_loading.save_metadata_file"):
                                    result = await downloader.download_attachment(
                                        mock_standard_file_message, download_required=True
                                    )

                                    assert result == {}
                                    mock_download.assert_called_once_with(mock_standard_file_message, file_path)

    class TestDownloadMethods:
        """Tests for specific download methods"""

        @pytest.mark.asyncio
        async def test_download_standard_file(self, downloader, mock_standard_file_message):
            """Test standard file download method"""
            file_path = "test_file.jpg"

            with patch("os.path.exists", return_value=True):
                with patch("os.path.getsize", return_value=12345):
                    await downloader._download_standard_file(mock_standard_file_message, file_path)

                    downloader.client.download_media.assert_called_once_with(
                        mock_standard_file_message.media, file=file_path
                    )

        @pytest.mark.asyncio
        async def test_download_large_file(self, downloader, mock_large_file_message):
            """Test large file download method"""
            file_path = "test_large_file.mp4"
            temp_path = f"{file_path}.partial"

            with patch("os.path.exists", return_value=False):  # No partial file
                with patch("builtins.open", mock_open()) as mock_file:
                    with patch("os.rename") as mock_rename:
                        with patch("os.path.getsize", return_value=60 * 1024 * 1024):
                            await downloader._download_large_file(mock_large_file_message, file_path)

                            call_args = downloader.client.download_media.call_args
                            assert call_args[0][0] == mock_large_file_message.media
                            assert "file" in call_args[1]
                            assert "offset" in call_args[1]
                            assert "progress_callback" in call_args[1]
                            assert "part_size_kb" in call_args[1]

                            mock_file.assert_called_once_with(temp_path, "wb")
                            mock_rename.assert_called_once_with(temp_path, file_path)

        @pytest.mark.asyncio
        async def test_download_large_file_with_resume(self, downloader, mock_large_file_message):
            """Test resuming a large file download"""
            file_path = "test_large_file.mp4"
            temp_path = f"{file_path}.partial"

            with patch("os.path.exists", return_value=True):
                with patch("os.path.getsize", return_value=30 * 1024 * 1024):  # 30 MB downloaded
                    with patch("builtins.open", mock_open()) as mock_file:
                        with patch("os.rename") as mock_rename:
                            await downloader._download_large_file(mock_large_file_message, file_path)

                            call_args = downloader.client.download_media.call_args
                            assert call_args[1]["offset"] == 30 * 1024 * 1024

                            mock_file.assert_called_once_with(temp_path, "ab")
                            mock_rename.assert_called_once_with(temp_path, file_path)

        @pytest.mark.asyncio
        async def test_download_large_file_error(self, downloader, mock_large_file_message):
            """Test error handling in large file download"""
            file_path = "test_large_file.mp4"
            temp_path = f"{file_path}.partial"

            # Mock file operations
            with patch("os.path.exists", side_effect=[False, True]):  # No partial file, but after error it exists
                with patch("builtins.open", mock_open()) as mock_file:
                    downloader.client.download_media.side_effect = Exception("Test download error")

                    with patch("os.path.getsize", return_value=10 * 1024 * 1024):  # 10 MB partial
                        with patch("logging.error") as mock_log_error:
                            with patch("logging.info") as mock_log_info:
                                await downloader._download_large_file(mock_large_file_message, file_path)

                                assert mock_log_error.called
                                assert mock_log_info.called
                                assert any("Partial download saved" in str(call) for call in mock_log_info.call_args_list)
