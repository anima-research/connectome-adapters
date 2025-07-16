import aiohttp
import json
import logging
import os
import pytest

from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from src.adapters.zulip_adapter.event_processing.attachment_loaders.uploader import Uploader

class TestUploader:
    """Tests for the Zulip Uploader class"""

    @pytest.fixture
    def client_mock(self):
        """Create a mocked Zulip client"""
        client = MagicMock()
        client.api_key = "test_api_key"
        return client

    @pytest.fixture
    def uploader(self, zulip_config, client_mock):
        """Create an Uploader with mocked dependencies"""
        return Uploader(zulip_config, client_mock)

    @pytest.fixture
    def sample_standard_attachment(self):
        """Create sample document attachment info"""
        return {
            "attachment_type": "document",
            "file_path": "/test/path/document123.pdf",
            "size": 12345
        }

    @pytest.fixture
    def mock_upload_response(self, expected_uri="/user_uploads/1/ab/xyz123/document.pdf"):
        """Create a mock Zulip upload response"""
        class MockResponse:
            status = 200

            async def json(self):
                return {"uri": expected_uri}

            async def text(self):
                return "Test response text"

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        return MockResponse()

    @pytest.fixture
    def session_mock(self, mock_upload_response):
        """Create a mocked Zulip session"""
        class MockSession:
            def __init__(self):
                self.post_called = False
                self.post_args = None
                self.post_kwargs = None

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            def post(self, *args, **kwargs):
                self.post_called = True
                self.post_args = args
                self.post_kwargs = kwargs
                return mock_upload_response

        return MockSession()

    @pytest.fixture
    def mock_magic_instance(self):
        """Create a Downloader with mocked dependencies"""
        mock_magic = MagicMock()
        mock_magic.from_file.return_value = "application/pdf"
        return mock_magic

    @pytest.mark.asyncio
    @pytest.mark.filterwarnings("ignore::RuntimeWarning")
    async def test_upload_file_success(self, uploader, session_mock, mock_magic_instance):
        """Test successful file upload"""
        file_path = "/test/path/document.pdf"

        with patch("aiohttp.ClientSession", return_value=session_mock):
            with patch("builtins.open", mock_open(read_data=b"test file content")):
                with patch("aiohttp.FormData", return_value=MagicMock()):
                    with patch("aiohttp.BasicAuth", return_value=MagicMock()):
                        with patch("magic.Magic", return_value=mock_magic_instance):
                            with patch.object(uploader, "_get_api_key", return_value="test_api_key"):
                                result = await uploader._upload_file(file_path)

                                assert "uri" in result
                                assert "document.pdf" in result["uri"]

                                assert session_mock.post_called, "session.post was not called"
                                assert session_mock.post_args[0].endswith("/api/v1/user_uploads"), \
                                    f"Unexpected URL: {session_mock.post_args[0]}"
                                assert "auth" in session_mock.post_kwargs, "auth parameter missing"
                                assert "data" in session_mock.post_kwargs, "data parameter missing"

    @pytest.mark.asyncio
    @pytest.mark.filterwarnings("ignore::RuntimeWarning")
    async def test_upload_file_exception(self, uploader, mock_magic_instance):
        """Test handling exception during upload"""
        file_path = "/test/path/document.pdf"

        session_mock = AsyncMock()
        session_mock.__aenter__.return_value = session_mock
        session_mock.post.side_effect = Exception("Connection error")

        with patch("aiohttp.ClientSession", return_value=session_mock):
            with patch("builtins.open", mock_open(read_data=b'test file content')):
                with patch("magic.Magic", return_value=mock_magic_instance):
                    with patch.object(logging, "error") as mock_log:
                        assert await uploader._upload_file(file_path) == {}
                        assert mock_log.called
                        assert "Error in manual upload" in mock_log.call_args[0][0]
