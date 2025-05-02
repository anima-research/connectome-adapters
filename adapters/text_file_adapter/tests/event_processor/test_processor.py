import asyncio
import json
import os
import pytest
import shutil
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

from adapters.text_file_adapter.adapter.event_processor.processor import Processor, FileEventType
from adapters.text_file_adapter.adapter.event_processor.file_event_cache import FileEventCache
from adapters.text_file_adapter.adapter.event_processor.file_validator import FileValidator

class TestProcessor:
    """Tests for the Text File Adapter Processor class"""

    @pytest.fixture(scope="class", autouse=True)
    def ensure_test_directories(self):
        """Create necessary test directories before tests and clean up after"""
        os.makedirs("test_files", exist_ok=True)
        os.makedirs("test_files/subdir", exist_ok=True)
        os.makedirs("test_backups", exist_ok=True)

        with open("test_files/test.txt", "w") as f:
            f.write("Test content")

        with open("test_files/test2.txt", "w") as f:
            f.write("Line 1\nLine 2\nLine 3\n")

        yield

        if os.path.exists("test_files"):
            shutil.rmtree("test_files")
        if os.path.exists("test_backups"):
            shutil.rmtree("test_backups")

    @pytest.fixture
    def test_file_paths(self):
        """Return test file paths"""
        return {
            "test_file": os.path.abspath("test_files/test.txt"),
            "test_file2": os.path.abspath("test_files/test2.txt"),
            "new_file": os.path.abspath("test_files/new_file.txt"),
            "move_dest": os.path.abspath("test_files/moved_file.txt"),
            "test_dir": os.path.abspath("test_files"),
            "test_subdir": os.path.abspath("test_files/subdir")
        }

    @pytest.fixture
    def file_event_cache_mock(self):
        """Create a mocked FileEventCache"""
        cache = AsyncMock(spec=FileEventCache)
        cache.record_create_event = AsyncMock()
        cache.record_update_event = AsyncMock()
        cache.record_delete_event = AsyncMock()
        cache.record_move_event = AsyncMock()
        cache.undo_recorded_event = AsyncMock(return_value=True)
        return cache

    @pytest.fixture
    def mock_config(self):
        """Create a mock config for testing"""
        config = MagicMock()
        config.get_setting.side_effect = lambda section, key: {
            ("adapter", "base_directory"): "/home/user/connectome-adapters",
            ("adapter", "allowed_directories"): ["/home/user/"],
            ("adapter", "max_file_size"): 5,  # 5 MB
            ("adapter", "max_token_count"): 1000,
            ("adapter", "security_mode"): "unrestricted",
            ("adapter", "allowed_extensions"): ["txt", "py", "md"],
            ("adapter", "blocked_extensions"): ["exe", "dll", "sh"],
            ("adapter", "backup_directory"): "test_backups"
        }.get((section, key))
        return config

    @pytest.fixture
    def processor(self, mock_config, file_event_cache_mock):
        """Create a Processor with mocked dependencies"""
        return Processor(mock_config, file_event_cache_mock)

    class TestProcessEvent:
        """Tests for the process_event method"""

        @pytest.mark.asyncio
        @pytest.mark.parametrize("event_type", [
            FileEventType.VIEW,
            FileEventType.READ,
            FileEventType.CREATE,
            FileEventType.DELETE,
            FileEventType.MOVE,
            FileEventType.UPDATE,
            FileEventType.INSERT,
            FileEventType.REPLACE,
            FileEventType.UNDO
        ])
        async def test_process_event_calls_correct_handler(self, processor, event_type):
            """Test that process_event calls the correct handler method"""
            data = {"test": "data"}
            handler_mocks = {}

            for handler_type in FileEventType:
                method_name = f"_handle_{handler_type.value}_event"
                handler_mock = AsyncMock(return_value={"request_completed": True})
                handler_mocks[handler_type] = handler_mock
                setattr(processor, method_name, handler_mock)

            result = await processor.process_event(event_type, data)
            assert result["request_completed"] is True
            handler_mocks[event_type].assert_called_once_with(data)

        @pytest.mark.asyncio
        async def test_process_unknown_event_type(self, processor):
            """Test handling an unknown event type"""
            result = await processor.process_event("unknown_type", {})
            assert result["request_completed"] is False

    class TestViewOperation:
        """Tests for the view operation"""

        @pytest.mark.asyncio
        async def test_view_directory_success(self, processor, test_file_paths):
            """Test successfully viewing a directory"""
            data = {"path": test_file_paths["test_dir"]}

            result = await processor._handle_view_event(data)
            assert result["request_completed"] is True
            assert "files" in result
            assert "directories" in result
            assert "test.txt" in result["files"]
            assert "test2.txt" in result["files"]
            assert "subdir" in result["directories"]

        @pytest.mark.asyncio
        async def test_view_nonexistent_directory(self, processor):
            """Test viewing a nonexistent directory"""
            result = await processor._handle_view_event({"path": "/nonexistent/dir"})
            assert result["request_completed"] is False

        @pytest.mark.asyncio
        async def test_view_file_instead_of_directory(self, processor, test_file_paths):
            """Test viewing a file instead of a directory"""
            data = {"path": test_file_paths["test_file"]}
            result = await processor._handle_view_event(data)
            assert result["request_completed"] is False

        @pytest.mark.asyncio
        async def test_view_missing_path(self, processor):
            """Test viewing with missing path"""
            result = await processor._handle_view_event({})
            assert result["request_completed"] is False

    class TestReadOperation:
        """Tests for the read operation"""

        @pytest.mark.asyncio
        async def test_read_file_success(self, processor, test_file_paths):
            """Test successfully reading a file"""
            data = {"path": test_file_paths["test_file"]}

            with patch.object(FileValidator, "validate", return_value=True):
                result = await processor._handle_read_event(data)
                assert result["request_completed"] is True
                assert result["content"] == "Test content"

        @pytest.mark.asyncio
        async def test_read_file_validation_failure(self, processor, test_file_paths):
            """Test reading a file that fails validation"""
            data = {"path": test_file_paths["test_file"]}

            with patch.object(FileValidator, "validate", return_value=False):
                result = await processor._handle_read_event(data)
                assert result["request_completed"] is False

        @pytest.mark.asyncio
        async def test_read_nonexistent_file(self, processor):
            """Test reading a nonexistent file"""
            result = await processor._handle_read_event({"path": "/nonexistent/file.txt"})
            assert result["request_completed"] is False

        @pytest.mark.asyncio
        async def test_read_missing_path(self, processor):
            """Test reading with missing path"""
            result = await processor._handle_read_event({})
            assert result["request_completed"] is False

    class TestCreateOperation:
        """Tests for the create operation"""

        @pytest.mark.asyncio
        async def test_create_file_success(self, processor, test_file_paths):
            """Test successfully creating a file"""
            new_file_path = test_file_paths["new_file"]
            data = {
                "path": new_file_path,
                "content": "New file content"
            }

            if os.path.exists(new_file_path):
                os.remove(new_file_path)

            result = await processor._handle_create_event(data)

            assert result["request_completed"] is True
            assert os.path.exists(new_file_path)

            with open(new_file_path, "r") as f:
                content = f.read()
                assert content == "New file content"

            processor.file_event_cache.record_create_event.assert_called_once_with(new_file_path)

        @pytest.mark.asyncio
        async def test_create_file_missing_fields(self, processor):
            """Test creating a file with missing fields"""
            data = {"path": "test_files/missing_content.txt"}
            result = await processor._handle_create_event(data)
            assert result["request_completed"] is False
            assert not os.path.exists("test_files/missing_content.txt")

            data = {"content": "Content without path"}
            result = await processor._handle_create_event(data)
            assert result["request_completed"] is False

        @pytest.mark.asyncio
        async def test_create_file_in_nonexistent_directory(self, processor):
            """Test creating a file in a nonexistent directory"""
            data = {
                "path": "test_files/nonexistent_dir/test.txt",
                "content": "Content in nonexistent dir"
            }
            result = await processor._handle_create_event(data)

            assert result["request_completed"] is True
            assert os.path.exists("test_files/nonexistent_dir/test.txt")
            processor.file_event_cache.record_create_event.assert_called_once()

    class TestDeleteOperation:
        """Tests for the delete operation"""

        @pytest.mark.asyncio
        async def test_delete_file_success(self, processor, test_file_paths):
            """Test successfully deleting a file"""
            temp_file = os.path.join(test_file_paths["test_dir"], "to_delete.txt")
            with open(temp_file, "w") as f:
                f.write("File to delete")

            data = {"path": temp_file}
            result = await processor._handle_delete_event(data)

            assert result["request_completed"] is True
            assert not os.path.exists(temp_file)
            processor.file_event_cache.record_delete_event.assert_called_once_with(temp_file)

        @pytest.mark.asyncio
        async def test_delete_nonexistent_file(self, processor):
            """Test deleting a nonexistent file"""
            result = await processor._handle_delete_event({"path": "/nonexistent/file.txt"})
            assert result["request_completed"] is False

        @pytest.mark.asyncio
        async def test_delete_missing_path(self, processor):
            """Test deleting with missing path"""
            result = await processor._handle_delete_event({})
            assert result["request_completed"] is False

    class TestMoveOperation:
        """Tests for the move operation"""

        @pytest.mark.asyncio
        async def test_move_file_success(self, processor, test_file_paths):
            """Test successfully moving a file"""
            source_path = os.path.join(test_file_paths["test_dir"], "to_move.txt")
            dest_path = test_file_paths["move_dest"]

            with open(source_path, "w") as f:
                f.write("File to move")

            data = {
                "source_path": source_path,
                "destination_path": dest_path
            }
            result = await processor._handle_move_event(data)

            assert result["request_completed"] is True
            assert not os.path.exists(source_path)
            assert os.path.exists(dest_path)

            with open(dest_path, "r") as f:
                content = f.read()
                assert content == "File to move"

            processor.file_event_cache.record_move_event.assert_called_once_with(
                source_path, dest_path
            )

        @pytest.mark.asyncio
        async def test_move_to_nonexistent_directory(self, processor, test_file_paths):
            """Test moving a file to a nonexistent directory"""
            source_path = os.path.join(test_file_paths["test_dir"], "move_to_new_dir.txt")
            dest_path = os.path.join(test_file_paths["test_dir"], "nonexistent_dir", "moved.txt")

            with open(source_path, 'w') as f:
                f.write("File to move to new dir")

            data = {
                "source_path": source_path,
                "destination_path": dest_path
            }
            result = await processor._handle_move_event(data)

            assert result["request_completed"] is True
            assert not os.path.exists(source_path)
            assert os.path.exists(dest_path)
            processor.file_event_cache.record_move_event.assert_called_once_with(
                source_path, dest_path
            )

        @pytest.mark.asyncio
        async def test_move_nonexistent_file(self, processor, test_file_paths):
            """Test moving a nonexistent file"""
            data = {
                "source_path": "/nonexistent/file.txt",
                "destination_path": test_file_paths["move_dest"]
            }
            result = await processor._handle_move_event(data)
            assert result["request_completed"] is False

        @pytest.mark.asyncio
        async def test_move_missing_fields(self, processor):
            """Test moving with missing fields"""
            data = {"source_path": "test_files/test.txt"}
            result = await processor._handle_move_event(data)
            assert result["request_completed"] is False

            data = {"destination_path": "test_files/missing_source.txt"}
            result = await processor._handle_move_event(data)
            assert result["request_completed"] is False

    class TestUpdateOperation:
        """Tests for the update operation"""

        @pytest.mark.asyncio
        async def test_update_file_success(self, processor, test_file_paths):
            """Test successfully updating a file"""
            data = {
                "path": test_file_paths["test_file"],
                "content": "Updated content"
            }
            result = await processor._handle_update_event(data)

            assert result["request_completed"] is True
            with open(test_file_paths["test_file"], 'r') as f:
                content = f.read()
                assert content == "Updated content"
            processor.file_event_cache.record_update_event.assert_called_once_with(
                test_file_paths["test_file"]
            )

        @pytest.mark.asyncio
        async def test_update_nonexistent_file(self, processor):
            """Test updating a nonexistent file"""
            data = {
                "path": "/nonexistent/file.txt",
                "content": "Updated content"
            }
            result = await processor._handle_update_event(data)
            assert result["request_completed"] is False

        @pytest.mark.asyncio
        async def test_update_missing_fields(self, processor, test_file_paths):
            """Test updating with missing fields"""
            # Missing content
            data = {"path": test_file_paths["test_file"]}
            result = await processor._handle_update_event(data)
            assert result["request_completed"] is False

            # Missing path
            data = {"content": "Content without path"}
            result = await processor._handle_update_event(data)
            assert result["request_completed"] is False

    class TestInsertOperation:
        """Tests for the insert operation"""

        @pytest.mark.asyncio
        async def test_insert_beginning_of_file(self, processor, test_file_paths):
            """Test inserting at the beginning of a file"""
            data = {
                "path": test_file_paths["test_file2"],
                "line": 0,
                "content": "Inserted at beginning\n"
            }
            result = await processor._handle_insert_event(data)

            assert result["request_completed"] is True
            with open(test_file_paths["test_file2"], "r") as f:
                content = f.read()
                assert content.startswith("Inserted at beginning\n")
                assert "Line 1" in content

            processor.file_event_cache.record_update_event.assert_called_once_with(
                test_file_paths["test_file2"]
            )

        @pytest.mark.asyncio
        async def test_insert_middle_of_file(self, processor, test_file_paths):
            """Test inserting in the middle of a file"""
            with open(test_file_paths["test_file2"], "w") as f:
                f.write("Line 1\nLine 2\nLine 3\n")

            data = {
                "path": test_file_paths["test_file2"],
                "line": 2,  # After Line 2
                "content": "Inserted in middle\n"
            }
            result = await processor._handle_insert_event(data)

            assert result["request_completed"] is True
            with open(test_file_paths["test_file2"], "r") as f:
                lines = f.readlines()
                assert lines[2] == "Inserted in middle\n"
                assert lines[3] == "Line 3\n"

        @pytest.mark.asyncio
        async def test_insert_end_of_file(self, processor, test_file_paths):
            """Test inserting at the end of a file"""
            with open(test_file_paths["test_file2"], "w") as f:
                f.write("Line 1\nLine 2\nLine 3\n")

            data = {
                "path": test_file_paths["test_file2"],
                "line": 10,  # Beyond end of file
                "content": "Inserted at end\n"
            }

            result = await processor._handle_insert_event(data)

            assert result["request_completed"] is True
            with open(test_file_paths["test_file2"], "r") as f:
                content = f.read()
                assert content.endswith("Inserted at end\n")

        @pytest.mark.asyncio
        async def test_insert_missing_fields(self, processor, test_file_paths):
            """Test inserting with missing fields"""
            # Missing line
            data = {
                "path": test_file_paths["test_file2"],
                "content": "Missing line number"
            }
            result = await processor._handle_insert_event(data)
            assert result["request_completed"] is False

            # Missing path
            data = {
                "line": 1,
                "content": "Missing path"
            }
            result = await processor._handle_insert_event(data)
            assert result["request_completed"] is False

    class TestReplaceOperation:
        """Tests for the replace operation"""

        @pytest.mark.asyncio
        async def test_replace_text_success(self, processor, test_file_paths):
            """Test successfully replacing text in a file"""
            with open(test_file_paths["test_file"], "w") as f:
                f.write("Original text to replace")

            data = {
                "path": test_file_paths["test_file"],
                "old_string": "Original",
                "new_string": "Replaced"
            }
            result = await processor._handle_replace_event(data)

            assert result["request_completed"] is True
            with open(test_file_paths["test_file"], "r") as f:
                content = f.read()
                assert "Replaced text to replace" in content
                assert "Original" not in content

            processor.file_event_cache.record_update_event.assert_called_once_with(
                test_file_paths["test_file"]
            )

        @pytest.mark.asyncio
        async def test_replace_nonexistent_text(self, processor, test_file_paths):
            """Test replacing text that doesn't exist in the file"""
            with open(test_file_paths["test_file"], "w") as f:
                f.write("Text that doesn't contain the pattern")

            data = {
                "path": test_file_paths["test_file"],
                "old_string": "nonexistent pattern",
                "new_string": "replacement"
            }
            result = await processor._handle_replace_event(data)

            assert result["request_completed"] is True
            with open(test_file_paths["test_file"], "r") as f:
                content = f.read()
                assert content == "Text that doesn't contain the pattern"

            processor.file_event_cache.record_update_event.assert_called_once_with(
                test_file_paths["test_file"]
            )

        @pytest.mark.asyncio
        async def test_replace_multiple_occurrences(self, processor, test_file_paths):
            """Test replacing multiple occurrences of text"""
            with open(test_file_paths["test_file"], "w") as f:
                f.write("Replace this and replace this again, and replace one more time")

            data = {
                "path": test_file_paths["test_file"],
                "old_string": "replace",
                "new_string": "REPLACED"
            }
            result = await processor._handle_replace_event(data)

            assert result["request_completed"] is True
            with open(test_file_paths["test_file"], "r") as f:
                content = f.read()
                assert content == "Replace this and REPLACED this again, and REPLACED one more time"

        @pytest.mark.asyncio
        async def test_replace_missing_fields(self, processor, test_file_paths):
            """Test replacing with missing fields"""
            # Missing old_string
            data = {
                "path": test_file_paths["test_file"],
                "new_string": "Replacement"
            }
            result = await processor._handle_replace_event(data)
            assert result["request_completed"] is False

            # Missing new_string
            data = {
                "path": test_file_paths["test_file"],
                "old_string": "Original"
            }
            result = await processor._handle_replace_event(data)
            assert result["request_completed"] is False

            # Missing path
            data = {
                "old_string": "Original",
                "new_string": "Replacement"
            }
            result = await processor._handle_replace_event(data)
            assert result["request_completed"] is False

    class TestUndoOperation:
        """Tests for the undo operation"""

        @pytest.mark.asyncio
        async def test_undo_success(self, processor, test_file_paths):
            """Test successfully undoing an operation"""
            data = {"path": test_file_paths["test_file"]}
            processor.file_event_cache.undo_recorded_event.return_value = True

            result = await processor._handle_undo_event(data)
            assert result["request_completed"] is True
            processor.file_event_cache.undo_recorded_event.assert_called_once_with(
                test_file_paths["test_file"]
            )

        @pytest.mark.asyncio
        async def test_undo_failure(self, processor, test_file_paths):
            """Test failing to undo an operation"""
            data = {"path": test_file_paths["test_file"]}
            processor.file_event_cache.undo_recorded_event.return_value = False

            result = await processor._handle_undo_event(data)
            assert result["request_completed"] is False
            processor.file_event_cache.undo_recorded_event.assert_called_once_with(
                test_file_paths["test_file"]
            )

        @pytest.mark.asyncio
        async def test_undo_nonexistent_file(self, processor):
            """Test undoing operations on a nonexistent file"""
            result = await processor._handle_undo_event({"path": "/nonexistent/file.txt"})
            assert result["request_completed"] is False

        @pytest.mark.asyncio
        async def test_undo_missing_path(self, processor):
            """Test undoing with missing path"""
            result = await processor._handle_undo_event({})
            assert result["request_completed"] is False

    class TestUtilityMethods:
        """Tests for utility methods"""

        def test_validate_fields_success(self, processor):
            """Test field validation success"""
            data = {
                "field1": "value1",
                "field2": "value2"
            }

            assert processor._validate_fields(data, ["field1", "field2"], "test_operation") is True

        def test_check_if_path_exists_success(self, processor, test_file_paths):
            """Test path existence check success"""
            assert processor._check_if_path_exists(test_file_paths["test_file"]) is True

        def test_check_if_path_exists_failure(self, processor):
            """Test path existence check failure"""
            with pytest.raises(ValueError):
                processor._check_if_path_exists("/nonexistent/file.txt")
