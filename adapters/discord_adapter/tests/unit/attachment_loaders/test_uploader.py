import logging
import os
import pytest

from unittest.mock import patch
from adapters.discord_adapter.adapter.attachment_loaders.uploader import Uploader

class TestUploader:
    """Tests for the Discord Uploader class"""

    @pytest.fixture
    def uploader(self, patch_config):
        """Create an Uploader with mocked dependencies"""
        return Uploader(patch_config)

    @pytest.fixture
    def sample_standard_attachment(self):
        """Create sample document attachment info"""
        return [
            {
                "attachment_type": "document",
                "file_path": "/test/path/document123.pdf",
                "size": 1000
            }
        ]

    def test_file_not_found(self, uploader, sample_standard_attachment):
        """Test handling missing file"""
        with patch("os.path.exists", return_value=False):
            with patch.object(logging, "error") as mock_log:
                result = uploader.upload_attachment(sample_standard_attachment)

                assert result == []
                assert mock_log.called
                assert "File not found" in mock_log.call_args[0][0]

    def test_file_too_large(self, uploader):
        """Test handling file that exceeds size limit"""
        oversized_attachment = [{
            "attachment_type": "video",
            "file_path": "/test/path/huge123.mp4",
            "size": 9 * 1024 * 1024  # 9MB, above 8MB limit
        }]

        with patch("os.path.exists", return_value=True):
            with patch.object(logging, "error") as mock_log:
                result = uploader.upload_attachment(oversized_attachment)

                assert result == []
                assert mock_log.called
                assert "exceeds Discord's size limit" in mock_log.call_args[0][0]

    def test_upload_file_success(self, uploader, sample_standard_attachment):
        """Test successful file upload"""
        with patch("os.path.exists", return_value=True):
            assert len(uploader.upload_attachment(sample_standard_attachment)) == 1
