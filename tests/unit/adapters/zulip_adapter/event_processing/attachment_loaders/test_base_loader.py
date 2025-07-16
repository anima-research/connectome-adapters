import pytest
import hashlib

from unittest.mock import MagicMock
from src.adapters.zulip_adapter.event_processing.attachment_loaders.base_loader import BaseLoader

class TestBaseLoader:
    """Tests for the Zulip BaseLoader class"""

    @pytest.fixture
    def client_mock(self):
        """Create a mocked Zulip client"""
        client = MagicMock()
        client.api_key = "test_api_key"
        return client

    @pytest.fixture
    def base_loader(self, zulip_config, client_mock):
        """Create a BaseLoader with mocked dependencies"""
        return BaseLoader(zulip_config, client_mock)

    @pytest.mark.parametrize("file_path,expected_id", [
        ("/user_uploads/1/ab/cdn7uXpQWsr1v5hInlSCU8PL/test.jpg", "cdn7uXpQWsr1v5hInlSCU8PL"),
        ("/simple/path/file.jpg", hashlib.md5(b"/simple/path/file.jpg").hexdigest()),
        ("", hashlib.md5(b"").hexdigest()),
    ])
    def test_generate_attachment_id(self, base_loader, file_path, expected_id):
        """Test generating attachment IDs from file paths"""
        assert base_loader._generate_attachment_id(file_path) == expected_id
