import json
import logging
import os
import pytest
import re

from datetime import datetime
from unittest.mock import MagicMock, patch

import src.core.utils.attachment_loading
from src.adapters.zulip_adapter.attachment_loaders.downloader import Downloader

class TestDownloader:
    """Tests for the Zulip Downloader class"""

    @pytest.fixture
    def client_mock(self):
        """Create a mocked Zulip client"""
        client = MagicMock()
        client.api_key = "test_api_key"
        return client

    @pytest.fixture
    def downloader(self, zulip_config, client_mock):
        """Create a Downloader with mocked dependencies"""
        return Downloader(zulip_config, client_mock)

    @pytest.fixture
    def mock_magic_instance(self):
        """Create a Downloader with mocked dependencies"""
        mock_magic = MagicMock()
        mock_magic.from_file.return_value = "text/plain"
        return mock_magic

    class TestDownloadAttachment:
        """Tests for the main download_attachment method"""

        @pytest.mark.asyncio
        async def test_download_attachment_new_file(self, downloader, mock_magic_instance):
            """Test downloading a new attachment"""
            message = {
                "content": "Check this file: [test.txt](/user_uploads/1/ab/xyz123/test.txt)"
            }

            with patch("os.path.exists", side_effect=[False, True]):  # File doesn't exist, then does after download
                with patch("src.core.utils.attachment_loading.create_attachment_dir"):
                    with patch.object(downloader, "_download_file", return_value=True) as mock_download:
                        with patch("src.core.utils.attachment_loading.save_metadata_file"):
                            with patch("magic.Magic", return_value=mock_magic_instance):
                                with patch("os.path.getsize", return_value=12345):
                                    result = await downloader.download_attachment(message)

                                    assert len(result) == 1
                                    assert result[0]["attachment_id"] == "xyz123"
                                    assert result[0]["size"] == 12345
                                    assert result[0]["content_type"] == "text/plain"
                                    mock_download.assert_called_once()

        @pytest.mark.asyncio
        async def test_download_attachment_existing_file(self, downloader, mock_magic_instance):
            """Test handling an existing attachment"""
            message = {
                "content": "Check this file: [test.txt](/user_uploads/1/ab/xyz123/test.txt)"
            }

            with patch("os.path.exists", return_value=True):  # File already exists
                with patch("src.core.utils.attachment_loading.save_metadata_file"):
                    with patch("magic.Magic", return_value=mock_magic_instance):
                        with patch("os.path.getsize", return_value=12345):
                            with patch.object(logging, "info") as mock_log:
                                result = await downloader.download_attachment(message)

                                assert len(result) == 1
                                assert result[0]["attachment_id"] == "xyz123"
                                assert result[0]["size"] == 12345
                                assert result[0]["content_type"] == "text/plain"
                                assert mock_log.called
                                assert "Skipping download" in mock_log.call_args_list[0][0][0]

        @pytest.mark.asyncio
        async def test_download_attachment_multiple_files(self, downloader, mock_magic_instance):
            """Test downloading multiple attachments"""
            message = {
                "content": "Here are files: [file1.txt](/user_uploads/1/cd/abc123/file1.txt) "
                           "and [file2.txt](/user_uploads/1/ef/def456/file2.txt)"
            }

            with patch("os.path.exists", return_value=False):  # Files don't exist
                with patch("src.core.utils.attachment_loading.create_attachment_dir"):
                    with patch.object(downloader, "_download_file", return_value=True) as mock_download:
                        with patch("src.core.utils.attachment_loading.save_metadata_file"):
                            with patch("magic.Magic", return_value=mock_magic_instance):
                                with patch("os.path.getsize", return_value=12345):
                                    result = await downloader.download_attachment(message)

                                    assert len(result) == 2
                                    assert result[0]["attachment_id"] == "abc123"
                                    assert result[1]["attachment_id"] == "def456"
                                    assert mock_download.call_count == 2

        @pytest.mark.asyncio
        async def test_download_attachment_no_attachments(self, downloader):
            """Test handling a message with no attachments"""
            assert await downloader.download_attachment({"content": "Just a plain text message"}) == []

    class TestUrlConstruction:
        """Tests for URL construction and API key handling"""

        def test_get_download_url(self, downloader):
            """Test download URL construction"""
            file_path = "/user_uploads/1/ab/xyz123/test.pdf"

            with patch.object(downloader, "_get_api_key", return_value="test_api_key"):
                url = downloader._get_download_url(file_path)

                assert url.startswith("https://zulip.example.com/user_uploads/")
                assert "api_key=test_api_key" in url

        def test_get_download_url_with_existing_query(self, downloader):
            """Test URL construction with existing query parameters"""
            file_path = "/user_uploads/test.pdf?version=1"

            with patch.object(downloader, "_get_api_key", return_value="test_api_key"):
                url = downloader._get_download_url(file_path)

                assert url.startswith("https://zulip.example.com/user_uploads/")
                assert "version=1" in url
                assert "api_key=test_api_key" in url
                assert "&api_key=" in url  # Should use & for additional params
