import json
import logging
import os
import pytest
import re

from datetime import datetime
from unittest.mock import MagicMock, patch

import core.utils.attachment_loading
from adapters.zulip_adapter.adapter.attachment_loaders.downloader import Downloader

class TestDownloader:
    """Tests for the Zulip Downloader class"""

    @pytest.fixture
    def client_mock(self):
        """Create a mocked Zulip client"""
        client = MagicMock()
        client.api_key = "test_api_key"
        return client

    @pytest.fixture
    def downloader(self, patch_config, client_mock):
        """Create a Downloader with mocked dependencies"""
        return Downloader(patch_config, client_mock)

    class TestExtractAttachmentMetadata:
        """Tests for attachment metadata extraction"""

        @pytest.mark.asyncio
        async def test_get_attachment_metadata_single_attachment(self, downloader):
            """Test extracting metadata from a message with a single attachment"""
            message = {
                "content": "Check this file: [test.pdf](/user_uploads/1/ab/xyz123/test.pdf)"
            }

            with patch.object(downloader, "_generate_attachment_id", return_value="xyz123"):
                result = await downloader._get_attachment_metadata(message)

                assert len(result) == 1
                assert result[0]["attachment_type"] == "document"
                assert result[0]["attachment_id"] == "xyz123"
                assert result[0]["file_name"] == "test.pdf"
                assert result[0]["file_extension"] == "pdf"
                assert result[0]["file_path"] == "/user_uploads/1/ab/xyz123/test.pdf"

        @pytest.mark.asyncio
        async def test_get_attachment_metadata_multiple_attachments(self, downloader):
            """Test extracting metadata from a message with multiple attachments"""
            message = {
                "content": "Here are some files: [image.jpg](/user_uploads/1/cd/abc123/image.jpg) "
                          "and [document.docx](/user_uploads/1/ef/def456/document.docx)"
            }

            attachment_ids = ["abc123", "def456"]
            with patch.object(downloader, "_generate_attachment_id", side_effect=attachment_ids):
                result = await downloader._get_attachment_metadata(message)

                assert len(result) == 2
                assert result[0]["attachment_type"] == "image"
                assert result[0]["file_name"] == "image.jpg"
                assert result[1]["attachment_type"] == "document"
                assert result[1]["file_name"] == "document.docx"

        @pytest.mark.asyncio
        async def test_get_attachment_metadata_no_attachments(self, downloader):
            """Test extracting metadata from a message with no attachments"""
            message = {
                "content": "This is a message with no attachments"
            }

            assert await downloader._get_attachment_metadata(message) == []

    class TestDownloadAttachment:
        """Tests for the main download_attachment method"""

        @pytest.mark.asyncio
        async def test_download_attachment_new_file(self, downloader):
            """Test downloading a new attachment"""
            message = {
                "content": "Check this file: [test.pdf](/user_uploads/1/ab/xyz123/test.pdf)"
            }

            metadata = {
                "attachment_id": "xyz123",
                "attachment_type": "document",
                "file_name": "test.pdf",
                "file_extension": "pdf",
                "file_path": "/user_uploads/1/ab/xyz123/test.pdf",
                "created_at": datetime.now()
            }

            with patch.object(downloader, "_get_attachment_metadata", return_value=[metadata]):
                with patch("os.path.exists", side_effect=[False, True]):  # File doesn't exist, then does after download
                    with patch("core.utils.attachment_loading.create_attachment_dir"):
                        with patch.object(downloader, "_download_file", return_value=True) as mock_download:
                            with patch("core.utils.attachment_loading.save_metadata_file"):
                                with patch("os.path.getsize", return_value=12345):
                                    with patch.object(logging, "info") as mock_log:
                                        result = await downloader.download_attachment(message)

                                        assert len(result) == 1
                                        assert result[0]["attachment_id"] == "xyz123"
                                        assert result[0]["size"] == 12345

                                        mock_download.assert_called_once()

                                        assert mock_log.called
                                        assert "Downloaded" in mock_log.call_args_list[0][0][0]

        @pytest.mark.asyncio
        async def test_download_attachment_existing_file(self, downloader):
            """Test handling an existing attachment"""
            message = {
                "content": "Check this file: [test.pdf](/user_uploads/1/ab/xyz123/test.pdf)"
            }

            metadata = {
                "attachment_id": "xyz123",
                "attachment_type": "document",
                "file_name": "test.pdf",
                "file_extension": "pdf",
                "file_path": "/user_uploads/1/ab/xyz123/test.pdf",
                "created_at": datetime.now()
            }

            with patch.object(downloader, "_get_attachment_metadata", return_value=[metadata]):
                with patch("os.path.exists", return_value=True):  # File already exists
                    with patch("core.utils.attachment_loading.save_metadata_file"):
                        with patch("os.path.getsize", return_value=12345):
                            with patch.object(logging, "info") as mock_log:
                                result = await downloader.download_attachment(message)

                                assert len(result) == 1
                                assert result[0]["attachment_id"] == "xyz123"
                                assert result[0]["size"] == 12345
                                assert mock_log.called
                                assert "Skipping download" in mock_log.call_args_list[0][0][0]

        @pytest.mark.asyncio
        async def test_download_attachment_multiple_files(self, downloader):
            """Test downloading multiple attachments"""
            message = {
                "content": "Here are files: [image.jpg](/user_uploads/1/cd/abc123/image.jpg) "
                           "and [doc.pdf](/user_uploads/1/ef/def456/doc.pdf)"
            }

            metadata1 = {
                "attachment_id": "abc123",
                "attachment_type": "image",
                "file_name": "image.jpg",
                "file_extension": "jpg",
                "file_path": "/user_uploads/1/cd/abc123/image.jpg",
                "created_at": datetime.now()
            }

            metadata2 = {
                "attachment_id": "def456",
                "attachment_type": "document",
                "file_name": "doc.pdf",
                "file_extension": "pdf",
                "file_path": "/user_uploads/1/ef/def456/doc.pdf",
                "created_at": datetime.now()
            }

            with patch.object(downloader, "_get_attachment_metadata", return_value=[metadata1, metadata2]):
                with patch("os.path.exists", return_value=False):  # Files don't exist
                    with patch("core.utils.attachment_loading.create_attachment_dir"):
                        with patch.object(downloader, "_download_file", return_value=True) as mock_download:
                            with patch("core.utils.attachment_loading.save_metadata_file"):
                                with patch("os.path.getsize", return_value=12345):
                                    result = await downloader.download_attachment(message)

                                    assert len(result) == 2
                                    assert result[0]["attachment_id"] == "abc123"
                                    assert result[1]["attachment_id"] == "def456"
                                    assert mock_download.call_count == 2

        @pytest.mark.asyncio
        async def test_download_attachment_no_attachments(self, downloader):
            """Test handling a message with no attachments"""
            message = {
                "content": "Just a plain text message"
            }

            with patch.object(downloader, "_get_attachment_metadata", return_value=[]):
                result = await downloader.download_attachment(message)
                assert result == []

    class TestUrlConstruction:
        """Tests for URL construction and API key handling"""

        def test_get_download_url(self, downloader):
            """Test download URL construction"""
            metadata = {
                "file_path": "/user_uploads/1/ab/xyz123/test.pdf"
            }

            with patch.object(downloader, "_get_api_key", return_value="test_api_key"):
                url = downloader._get_download_url(metadata)

                assert url.startswith("https://zulip.example.com/user_uploads/")
                assert "api_key=test_api_key" in url

        def test_get_download_url_with_existing_query(self, downloader):
            """Test URL construction with existing query parameters"""
            metadata = {
                "file_path": "/user_uploads/test.pdf?version=1"
            }

            with patch.object(downloader, "_get_api_key", return_value="test_api_key"):
                url = downloader._get_download_url(metadata)

                assert url.startswith("https://zulip.example.com/user_uploads/")
                assert "version=1" in url
                assert "api_key=test_api_key" in url
                assert "&api_key=" in url  # Should use & for additional params
