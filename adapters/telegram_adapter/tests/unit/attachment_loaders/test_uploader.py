import os
import pytest
import shutil
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

import core.utils.attachment_loading
from adapters.telegram_adapter.adapter.attachment_loaders.uploader import Uploader
from core.events.models.outgoing_events import OutgoingAttachmentInfo

class TestUploader:
    """Tests for the Uploader class"""

    @pytest.fixture(scope="class", autouse=True)
    def ensure_test_directories(self):
        """Create necessary test directories before tests and clean up after"""
        os.makedirs("test_attachments", exist_ok=True)
        os.makedirs("test_attachments/document", exist_ok=True)
        os.makedirs("test_attachments/tmp_uploads", exist_ok=True)

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
        return OutgoingAttachmentInfo(file_name="file1.txt", content="dGVzdAo=")

    @pytest.fixture
    def mock_telegram_message(self):
        """Create a mock Telegram message returned after sending a file"""
        message = MagicMock()
        message.id = "msg123"
        photo = MagicMock()
        photo.id = "uploaded_media_id"
        message.photo = photo
        return message

    @pytest.mark.asyncio
    async def test_no_conversation(self, uploader, sample_standard_attachment):
        """Test handling missing conversation"""
        with patch("os.path.exists", return_value=True):
            assert await uploader.upload_attachment(None, sample_standard_attachment) == {}
            uploader.client.send_file.assert_not_called()

    @pytest.mark.asyncio
    async def test_upload_file(self, uploader, sample_standard_attachment, mock_telegram_message):
        """Test uploading a standard photo"""
        uploader.client.send_file.return_value = mock_telegram_message

        attachment_dir = "test_attachments/photo/uploaded_media_id"
        dir_path = "/test/path"

        with patch("os.path.exists", side_effect=lambda path: path != dir_path):
            metadata = {
                "attachment_id": "file1_id",
                "attachment_type": "document",
                "filename": "file1_id.txt",
                "size": 12345,
                "content_type": None,
                "content": None,
                "url": None,
                "created_at": datetime.now(),
                "processable": True
            }
            with patch.object(uploader, "_get_attachment_metadata", return_value=metadata) as mock_metadata:
                with patch("core.utils.attachment_loading.create_attachment_dir"):
                    with patch("core.utils.attachment_loading.move_attachment"):
                        with patch("os.path.join", return_value=attachment_dir):
                            with patch("os.path.dirname", return_value=dir_path):
                                with patch("os.listdir", return_value=[]):
                                    with patch("magic.Magic") as mock_magic:
                                        mock_magic_instance = mock_magic.return_value
                                        mock_magic_instance.from_file.return_value = "text/plain"

                                        with patch("core.utils.attachment_loading.save_metadata_file"):
                                            result = await uploader.upload_attachment(
                                                "conversation", sample_standard_attachment
                                            )

                                            mock_metadata.assert_called_once_with(mock_telegram_message)
                                            assert result["attachment_id"] == "file1_id"
                                            assert result["attachment_type"] == "document"
                                            assert "message" in result

    @pytest.mark.asyncio
    async def test_upload_error_handling(self, uploader, sample_standard_attachment):
        """Test error handling during upload"""
        uploader.client.send_file.side_effect = Exception("Test upload error")

        with patch("os.path.exists", return_value=True):
            assert await uploader.upload_attachment("conversation", sample_standard_attachment) == {}
