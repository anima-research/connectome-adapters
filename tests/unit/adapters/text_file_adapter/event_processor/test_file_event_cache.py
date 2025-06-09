import asyncio
import os
import pytest
import shutil
import tempfile

from unittest.mock import MagicMock, AsyncMock, patch
from src.adapters.text_file_adapter.event_processor.file_event_cache import FileEventCache

class TestFileEventCache:
    """Tests for the FileEventCache class"""

    @pytest.fixture
    def setup_test_files(self):
        """Create test files for the event cache"""
        test_dir = tempfile.mkdtemp()
        backup_dir = os.path.join(test_dir, "backups")
        os.makedirs(backup_dir, exist_ok=True)

        # Create a test file
        test_file = os.path.join(test_dir, "test_file.txt")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("This is a test file content.")

        # Create another test file for move operations
        move_file = os.path.join(test_dir, "move_file.txt")
        with open(move_file, "w", encoding="utf-8") as f:
            f.write("This file will be moved.")

        yield {
            "test_dir": test_dir,
            "backup_dir": backup_dir,
            "test_file": test_file,
            "move_file": move_file
        }

        # Cleanup after tests
        try:
            shutil.rmtree(test_dir)
        except Exception as e:
            print(f"Error cleaning up test files: {e}")

    @pytest.fixture
    def mock_config(self, setup_test_files):
        """Create a mock config for testing"""
        def _create():
            config = MagicMock()
            config.get_setting.side_effect = lambda section, key: {
                ("adapter", "backup_directory"): setup_test_files["backup_dir"],
                ("adapter", "event_ttl_hours"): 0.0001,
                ("adapter", "cleanup_interval_hours"): 0.001,
                ("adapter", "max_events_per_file"): 2
            }.get((section, key))
            return config
        return _create

    @pytest.fixture
    def event_cache(self, mock_config):
        """Create a FileEventCache instance for testing"""
        return FileEventCache(mock_config(), start_maintenance=False)

    @pytest.mark.asyncio
    async def test_record_create_event(self, event_cache, setup_test_files):
        """Test recording a file creation event"""
        test_file = setup_test_files["test_file"]

        await event_cache.record_create_event(test_file)

        abs_path = os.path.abspath(test_file)
        assert abs_path in event_cache.event_cache
        assert len(event_cache.event_cache[abs_path]) == 1
        assert event_cache.event_cache[abs_path][0]["action"] == "delete"

    @pytest.mark.asyncio
    async def test_record_update_event(self, event_cache, setup_test_files):
        """Test recording a file update event"""
        test_file = setup_test_files["test_file"]

        await event_cache.record_update_event(test_file)

        abs_path = os.path.abspath(test_file)
        assert abs_path in event_cache.event_cache
        assert len(event_cache.event_cache[abs_path]) == 1

        event = event_cache.event_cache[abs_path][0]
        assert event["action"] == "update"
        assert "backup_info" in event
        assert os.path.exists(event["backup_info"]["backup_file_path"])

    @pytest.mark.asyncio
    async def test_record_delete_event(self, event_cache, setup_test_files):
        """Test recording a file deletion event"""
        test_file = setup_test_files["test_file"]

        await event_cache.record_delete_event(test_file)

        abs_path = os.path.abspath(test_file)
        assert abs_path in event_cache.event_cache
        assert len(event_cache.event_cache[abs_path]) == 1

        event = event_cache.event_cache[abs_path][0]
        assert event["action"] == "create"
        assert "backup_info" in event
        assert os.path.exists(event["backup_info"]["backup_file_path"])

    @pytest.mark.asyncio
    async def test_undo_nonexistent_event(self, event_cache, setup_test_files):
        """Test undoing when no events are recorded"""
        test_file = setup_test_files["test_file"]

        assert await event_cache.undo_recorded_event(test_file) is False

    @pytest.mark.asyncio
    async def test_undo_create_event(self, event_cache, setup_test_files):
        """Test undoing a file creation event (deletion)"""
        test_file = setup_test_files["test_file"]

        await event_cache.record_create_event(test_file)

        backup_copy = os.path.join(setup_test_files["test_dir"], "backup_copy.txt")
        shutil.copy2(test_file, backup_copy)

        result = await event_cache.undo_recorded_event(test_file)

        assert result is True
        assert not os.path.exists(test_file)

        shutil.copy2(backup_copy, test_file)

    @pytest.mark.asyncio
    async def test_undo_update_event(self, event_cache, setup_test_files):
        """Test undoing a file update event"""
        test_file = setup_test_files["test_file"]
        original_content = "This is a test file content."

        await event_cache.record_update_event(test_file)

        with open(test_file, "w", encoding="utf-8") as f:
            f.write("This is modified content.")

        result = await event_cache.undo_recorded_event(test_file)
        assert result is True
        with open(test_file, "r", encoding="utf-8") as f:
            restored_content = f.read()
        assert restored_content == original_content

    @pytest.mark.asyncio
    async def test_undo_delete_event(self, event_cache, setup_test_files):
        """Test undoing a file deletion event"""
        test_file = setup_test_files["test_file"]

        await event_cache.record_delete_event(test_file)

        os.remove(test_file)
        assert not os.path.exists(test_file)

        result = await event_cache.undo_recorded_event(test_file)
        assert result is True
        assert os.path.exists(test_file)

    @pytest.mark.asyncio
    async def test_max_events_enforcement(self, mock_config, setup_test_files):
        """Test that max_events_per_file is enforced"""
        cache = FileEventCache(mock_config(), start_maintenance=False)
        test_file = setup_test_files["test_file"]
        abs_path = os.path.abspath(test_file)

        await cache.record_create_event(test_file)  # This should be removed when max is reached
        await cache.record_update_event(test_file)
        await cache.record_update_event(test_file)

        assert len(cache.event_cache[abs_path]) == 2
        assert cache.event_cache[abs_path][0]["action"] == "update"
        assert cache.event_cache[abs_path][1]["action"] == "update"

    @pytest.mark.asyncio
    async def test_cleanup_expired_events(self, mock_config, setup_test_files):
        """Test cleaning up expired events"""
        cache = FileEventCache(mock_config(), start_maintenance=False)
        test_file = setup_test_files["test_file"]
        abs_path = os.path.abspath(test_file)

        await cache.record_update_event(test_file)
        assert abs_path in cache.event_cache

        await asyncio.sleep(0.5)
        await cache._cleanup_expired_events()
        assert abs_path not in cache.event_cache or not cache.event_cache[abs_path]

    @pytest.mark.asyncio
    async def test_backup_cleanup_after_undo(self, event_cache, setup_test_files):
        """Test that backups are cleaned up after undo"""
        test_file = setup_test_files["test_file"]
        await event_cache.record_update_event(test_file)

        abs_path = os.path.abspath(test_file)
        backup_info = event_cache.event_cache[abs_path][0]["backup_info"]
        backup_path = backup_info["backup_file_path"]

        assert os.path.exists(backup_path)

        await event_cache.undo_recorded_event(test_file)
        assert not os.path.exists(backup_path)
