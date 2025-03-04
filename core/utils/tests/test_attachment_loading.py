mport json
import logging
import os
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

from core.utils.attachment_loading import (
    create_attachment_dir,
    delete_empty_directory,
    get_attachment_type_by_extension,
    move_attachment,
    save_metadata_file
)

class TestAttachmentLoading:
    """Tests basic attachment loading functions"""

    def test_create_attachment_dir(self):
        """Test creating an attachment directory"""
        test_dir = "/path/to/attachments"

        with patch("os.makedirs") as mock_makedirs:
            create_attachment_dir(test_dir)
            mock_makedirs.assert_called_once_with(test_dir, exist_ok=True)

    def test_delete_empty_directory(self):
        """Test deleting an empty directory"""
        file_path = "/test/dir/file.pdf"

        with patch("os.path.dirname", return_value="/test/dir"):
            with patch("os.path.exists", return_value=True):
                with patch("os.listdir", return_value=[]):
                    with patch("os.rmdir") as mock_rmdir:
                        with patch.object(logging, "info") as mock_log:
                            delete_empty_directory(file_path)

                            mock_rmdir.assert_called_once_with("/test/dir")
                            assert mock_log.called
                            assert "Removed directory" in mock_log.call_args[0][0]

    def test_delete_empty_directory_not_empty(self):
        """Test not deleting a non-empty directory"""
        file_path = "/test/dir/file.pdf"

        with patch("os.path.dirname", return_value="/test/dir"):
            with patch("os.path.exists", return_value=True):
                with patch("os.listdir", return_value=["other_file.txt"]):
                    with patch("os.rmdir") as mock_rmdir:
                        delete_empty_directory(file_path)
                        mock_rmdir.assert_not_called()

    @pytest.mark.parametrize("extension,expected_type", [
        ("jpg", "image"),
        ("png", "image"),
        ("gif", "image"),
        ("mp4", "video"),
        ("mov", "video"),
        ("mp3", "audio"),
        ("wav", "audio"),
        ("pdf", "document"),
        ("docx", "document"),
        ("zip", "archive"),
        ("rar", "archive"),
        ("py", "code"),
        ("js", "code"),
        ("epub", "ebook"),
        ("ttf", "font"),
        ("obj", "3d_model"),
        ("exe", "executable"),
        ("tgs", "sticker"),
        ("unknown", "document"),  # Default for unknown extensions
        (None, "document")  # Default for no extension
    ])
    def test_get_attachment_type_by_extension(self, extension, expected_type):
        """Test attachment type detection by file extension"""
        assert get_attachment_type_by_extension(extension) == expected_type

    def test_move_attachment(self):
        """Test moving an attachment file"""
        src_path = "/test/source/file.pdf"
        dest_path = "/test/dest/file.pdf"

        with patch("shutil.move") as mock_move:
            move_attachment(src_path, dest_path)
            mock_move.assert_called_once_with(src_path, dest_path)

    def test_save_metadata_file(self):
        """Test creating a metadata file"""
        metadata = {
            "attachment_id": "test123",
            "attachment_type": "photo",
            "file_extension": "jpg",
            "created_at": datetime.now(),
            "size": 12345
        }
        attachment_dir = "/fake/path"

        with patch("builtins.open", mock_open()) as mock_file:
            with patch("json.dump") as mock_json_dump:
                save_metadata_file(metadata, attachment_dir)

                expected_path = os.path.join(attachment_dir, "test123.json")
                mock_file.assert_called_once_with(expected_path, "w")
                mock_json_dump.assert_called_once()

                args, kwargs = mock_json_dump.call_args
                assert args[0] == metadata  # First arg is the metadata
                assert kwargs.get("indent") == 2
                assert "default" in kwargs  # Should have a default serializer for datetime
