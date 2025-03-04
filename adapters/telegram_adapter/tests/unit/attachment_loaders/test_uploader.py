import os
import pytest
import shutil
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

import core.utils.attachment_loading
from adapters.telegram_adapter.adapter.attachment_loaders.uploader import Uploader

class TestUploader:
    """Tests for the Uploader class"""

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
        client.send_file = AsyncMock()
        return client

    @pytest.fixture
    def uploader(self, client_mock, patch_config):
        """Create an Uploader with mocked dependencies"""
        yield Uploader(patch_config, client_mock)

    @pytest.fixture
    def sample_standard_attachment(self):
        """Create sample photo attachment info"""
        return {
            "attachment_type": "photo",
            "file_path": "/test/path/photo123.jpg",
            "size": 12345
        }

    @pytest.fixture
    def sample_large_attachment(self):
        """Create sample large attachment info"""
        return {
            "attachment_type": "video",
            "file_path": "/test/path/large789.mp4",
            "size": 60 * 1024 * 1024  # 60MB
        }

    @pytest.fixture
    def mock_telegram_message(self):
        """Create a mock Telegram message returned after sending a file"""
        message = MagicMock()
        message.id = "msg123"
        photo = MagicMock()
        photo.id = "uploaded_media_id"
        message.photo = photo
        return message

    class TestUploadAttachment:
        """Tests for the upload_attachment method"""

        @pytest.mark.asyncio
        async def test_file_not_found(self, uploader, sample_standard_attachment):
            """Test handling missing file"""
            with patch("os.path.exists", return_value=False):
                result = await uploader.upload_attachment("conversation", sample_standard_attachment)

                assert result == {}
                uploader.client.send_file.assert_not_called()

        @pytest.mark.asyncio
        async def test_file_too_large(self, uploader):
            """Test handling file that exceeds size limit"""
            oversized_attachment = {
                "attachment_type": "video",
                "file_path": "/test/path/huge123.mp4",
                "size": 3000 * 1024 * 1024
            }

            with patch("os.path.exists", return_value=True):
                result = await uploader.upload_attachment("conversation", oversized_attachment)

                assert result == {}
                uploader.client.send_file.assert_not_called()

        @pytest.mark.asyncio
        async def test_no_conversation(self, uploader, sample_standard_attachment):
            """Test handling missing conversation"""
            with patch("os.path.exists", return_value=True):
                result = await uploader.upload_attachment(None, sample_standard_attachment)

                assert result == {}
                uploader.client.send_file.assert_not_called()

        @pytest.mark.asyncio
        async def test_upload_standard_file(self, uploader, sample_standard_attachment, mock_telegram_message):
            """Test uploading a standard photo"""
            attachment_dir = "test_attachments/photo/uploaded_media_id"
            dir_path = "/test/path"

            with patch("os.path.exists", side_effect=lambda path: path != dir_path):
                with patch.object(uploader, "_upload_standard_file", return_value=mock_telegram_message) as mock_upload:
                    metadata = {
                        "attachment_id": "uploaded_media_id",
                        "attachment_type": "photo",
                        "file_extension": "jpg",
                        "created_at": datetime.now(),
                        "size": 12345
                    }
                    with patch.object(uploader, "_get_attachment_metadata", return_value=metadata) as mock_metadata:
                        with patch("core.utils.attachment_loading.create_attachment_dir"):
                            with patch("core.utils.attachment_loading.save_metadata_file"):
                                with patch("core.utils.attachment_loading.move_attachment"):
                                    with patch("core.utils.attachment_loading.delete_empty_directory"):
                                        with patch("os.path.join", return_value=attachment_dir):
                                            with patch("os.path.dirname", return_value=dir_path):
                                                with patch("os.listdir", return_value=[]):
                                                    result = await uploader.upload_attachment(
                                                        "conversation", sample_standard_attachment
                                                    )

                                                    mock_upload.assert_called_once()
                                                    mock_metadata.assert_called_once_with(mock_telegram_message)

                                                    assert result["attachment_id"] == "uploaded_media_id"
                                                    assert result["attachment_type"] == "photo"
                                                    assert "message" in result

        @pytest.mark.asyncio
        async def test_upload_large_file(self, uploader, sample_large_attachment, mock_telegram_message):
            """Test uploading a large file"""
            attachment_dir = "test_attachments/photo/uploaded_media_id"
            dir_path = "/test/path"

            with patch("os.path.exists", side_effect=lambda path: path != dir_path):
                with patch.object(uploader, "_upload_large_file", return_value=mock_telegram_message) as mock_upload:
                    metadata = {
                        "attachment_id": "uploaded_media_id",
                        "attachment_type": "video",
                        "file_extension": "mp4",
                        "created_at": datetime.now(),
                        "size": 60 * 1024 * 1024
                    }
                    with patch.object(uploader, "_get_attachment_metadata", return_value=metadata) as mock_metadata:
                        with patch("core.utils.attachment_loading.create_attachment_dir"):
                            with patch("core.utils.attachment_loading.save_metadata_file"):
                                with patch("core.utils.attachment_loading.move_attachment"):
                                    with patch("core.utils.attachment_loading.delete_empty_directory"):
                                        with patch("os.path.join", return_value=attachment_dir):
                                            with patch("os.path.dirname", return_value=dir_path):
                                                with patch("os.listdir", return_value=[]):
                                                    result = await uploader.upload_attachment(
                                                        "conversation", sample_large_attachment
                                                    )

                                                    mock_upload.assert_called_once()
                                                    mock_metadata.assert_called_once_with(mock_telegram_message)

                                                    assert result["attachment_id"] == "uploaded_media_id"
                                                    assert result["attachment_type"] == "video"
                                                    assert "message" in result

        @pytest.mark.asyncio
        async def test_upload_error_handling(self, uploader, sample_standard_attachment):
            """Test error handling during upload"""
            with patch("os.path.exists", return_value=True):
                with patch.object(uploader, "_upload_standard_file",
                                  side_effect=Exception("Test upload error")):

                    assert await uploader.upload_attachment("conversation", sample_standard_attachment) == {}

    class TestUploadMethods:
        """Tests for specific upload methods"""

        @pytest.mark.asyncio
        async def test_upload_standard_file(self, uploader, sample_standard_attachment):
            """Test standard file upload method"""
            conversation = "test_conversation"
            upload_kwargs = {
                "file": sample_standard_attachment["file_path"],
                "force_document": False
            }

            uploader.client.send_file.return_value = "test_result"

            with patch("os.path.getsize", return_value=12345):
                result = await uploader._upload_standard_file(conversation, upload_kwargs)
                uploader.client.send_file.assert_called_once_with(
                    entity=conversation, **upload_kwargs
                )
                assert result == "test_result"

        @pytest.mark.asyncio
        async def test_upload_large_file(self, uploader, sample_large_attachment):
            """Test large file upload method"""
            conversation = "test_conversation"
            upload_kwargs = {
                "file": sample_large_attachment["file_path"],
                "force_document": True
            }

            uploader.client.send_file.return_value = "test_result"

            with patch("os.path.getsize", return_value=60 * 1024 * 1024):
                with patch("os.path.basename", return_value="large789.mp4"):
                    result = await uploader._upload_large_file(conversation, upload_kwargs)
                    uploader.client.send_file.assert_called_once()

                    call_args = uploader.client.send_file.call_args
                    assert call_args[1]["entity"] == conversation
                    assert call_args[1]["file"] == sample_large_attachment["file_path"]
                    assert call_args[1]["force_document"] is True
                    assert "progress_callback" in call_args[1]
                    assert call_args[1]["part_size_kb"] == 512
                    assert call_args[1]["use_cache"] is False
                    assert result == "test_result"
