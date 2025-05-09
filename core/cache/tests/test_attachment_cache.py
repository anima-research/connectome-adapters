import pytest
import asyncio
import os
import json
import shutil
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, PropertyMock

from core.cache.attachment_cache import AttachmentCache, CachedAttachment

class TestAttachmentCache:
    """Tests for the AttachmentCache"""

    @pytest.fixture
    def config_mock(self):
        """Create a mocked Config instance"""
        config = MagicMock()
        config.get_setting.side_effect = lambda section, key, default=None: {
            "attachments": {
                "storage_dir": "test_storage_dir",
                "max_age_days": 30,
                "max_total_attachments": 100,
                "cleanup_interval_hours": 24,
                "max_file_size_mb": 2048
            }
        }.get(section, {}).get(key, default)
        return config

    @pytest.fixture
    def attachment_cache(self, config_mock):
        """Create an AttachmentCache with mocked dependencies"""
        with patch.object(AttachmentCache, '_upload_existing_attachments'):
            return AttachmentCache(config_mock)

    @pytest.fixture
    def sample_attachment_info(self):
        """Create sample attachment info for tests"""
        return {
            "attachment_id": "test123",
            "attachment_type": "photo",
            "created_at": datetime.now(),
            "file_extension": "jpg",
            "size": 12345,
            "processable": True,
            "content": None
        }

    @pytest.fixture
    def cached_attachment(self, sample_attachment_info):
        """Create a sample CachedAttachment object"""
        attachment = CachedAttachment(
            attachment_id=sample_attachment_info["attachment_id"],
            attachment_type=sample_attachment_info["attachment_type"],
            created_at=sample_attachment_info["created_at"],
            file_extension=sample_attachment_info["file_extension"],
            size=sample_attachment_info["size"],
            processable=sample_attachment_info["processable"]
        )
        return attachment

    class TestAttachmentProperties:
        """Tests for CachedAttachment properties"""

        def test_file_path_with_extension(self, cached_attachment):
            """Test file_path property with extension"""
            expected_path = os.path.join(
                cached_attachment.attachment_type,
                cached_attachment.attachment_id,
                f"{cached_attachment.attachment_id}.{cached_attachment.file_extension}"
            )

            assert cached_attachment.file_path == expected_path

        def test_file_path_without_extension(self, cached_attachment):
            """Test file_path property without extension"""
            cached_attachment.file_extension = None
            expected_path = os.path.join(
                cached_attachment.attachment_type,
                cached_attachment.attachment_id,
                cached_attachment.attachment_id
            )

            assert cached_attachment.file_path == expected_path

        def test_metadata_path(self, cached_attachment):
            """Test metadata_path property"""
            expected_path = os.path.join(
                cached_attachment.attachment_type,
                cached_attachment.attachment_id,
                f"{cached_attachment.attachment_id}.json"
            )

            assert cached_attachment.metadata_path == expected_path

    class TestUploadExistingAttachments:
        """Tests for the _upload_existing_attachments method"""

        @pytest.fixture
        def test_storage_dir(self):
            """Create and clean up a test storage directory"""
            test_dir = "test_storage_dir"
            os.makedirs(test_dir, exist_ok=True)
            yield test_dir
            if os.path.exists(test_dir):
                shutil.rmtree(test_dir)

        @pytest.fixture
        def test_attachment_structure(self, test_storage_dir):
            """Create a test attachment directory structure with files"""
            # Create a photo directory
            photo_dir = os.path.join(test_storage_dir, "photo")
            os.makedirs(photo_dir, exist_ok=True)

            # Create an attachment directory
            attachment_id = "test_attachment_123"
            attachment_dir = os.path.join(photo_dir, attachment_id)
            os.makedirs(attachment_dir, exist_ok=True)

            # Create a sample file
            with open(os.path.join(attachment_dir, f"{attachment_id}.jpg"), "w") as f:
                f.write("test image content")

            # Create sample metadata
            metadata = {
                "attachment_id": attachment_id,
                "attachment_type": "photo",
                "created_at": datetime.now().isoformat(),
                "file_extension": "jpg",
                "size": 12345,
                "processable": True,
                "content": None
            }

            with open(os.path.join(attachment_dir, f"{attachment_id}.json"), "w") as f:
                json.dump(metadata, f)

            return attachment_id

        def test_directory_not_exists(self, config_mock):
            """Test handling when storage directory doesn't exist"""
            with patch('os.path.exists', return_value=False):
                cache = AttachmentCache(config_mock)
                assert len(cache.attachments) == 0

        def test_load_attachments(self, config_mock, test_attachment_structure):
            """Test loading attachments from directory structure"""
            cache = AttachmentCache(config_mock)
            assert test_attachment_structure in cache.attachments

            loaded_attachment = cache.attachments[test_attachment_structure]
            assert loaded_attachment.attachment_type == "photo"
            assert loaded_attachment.file_extension == "jpg"

    class TestAddAttachment:
        """Tests for the add_attachment method"""

        @pytest.mark.asyncio
        async def test_add_new_attachment(self, attachment_cache, sample_attachment_info):
            """Test adding a new attachment to the cache"""
            result = await attachment_cache.add_attachment("conv123", sample_attachment_info)

            assert sample_attachment_info["attachment_id"] in attachment_cache.attachments
            assert result.attachment_id == sample_attachment_info["attachment_id"]
            assert result.attachment_type == sample_attachment_info["attachment_type"]
            assert result.file_extension == sample_attachment_info["file_extension"]
            assert "conv123" in result.conversations

        @pytest.mark.asyncio
        async def test_add_existing_attachment_new_conversation(self, attachment_cache, sample_attachment_info):
            """Test adding an existing attachment for a new conversation"""
            await attachment_cache.add_attachment("conv123", sample_attachment_info)
            result = await attachment_cache.add_attachment("conv456", sample_attachment_info)

            assert "conv123" in result.conversations
            assert "conv456" in result.conversations
            assert len(attachment_cache.attachments) == 1

        @pytest.mark.asyncio
        async def test_add_existing_attachment_same_conversation(self, attachment_cache, sample_attachment_info):
            """Test adding an existing attachment for the same conversation again"""
            await attachment_cache.add_attachment("conv123", sample_attachment_info)
            result = await attachment_cache.add_attachment("conv123", sample_attachment_info)

            assert len(result.conversations) == 1
            assert "conv123" in result.conversations

    class TestRemoveAttachment:
        """Tests for the remove_attachment method"""

        @pytest.mark.asyncio
        async def test_remove_attachment_without_files(self, attachment_cache, sample_attachment_info):
            """Test removing an attachment from the cache"""
            await attachment_cache.add_attachment("conv123", sample_attachment_info)
            assert sample_attachment_info["attachment_id"] in attachment_cache.attachments

            with patch('os.path.exists', return_value=False):
                await attachment_cache.remove_attachment(sample_attachment_info["attachment_id"])
            assert sample_attachment_info["attachment_id"] not in attachment_cache.attachments

        @pytest.mark.asyncio
        async def test_remove_attachment_with_files(self, attachment_cache, sample_attachment_info):
            """Test removing an attachment including its files"""
            await attachment_cache.add_attachment("conv123", sample_attachment_info)

            with patch.object(CachedAttachment, 'file_path', new_callable=PropertyMock) as mock_file_path:
                with patch.object(CachedAttachment, 'metadata_path', new_callable=PropertyMock) as mock_metadata_path:
                    mock_file_path.return_value = "/fake/dir/test123.jpg"
                    mock_metadata_path.return_value = "/fake/dir/test123.json"

                    with patch('os.path.exists', return_value=True):
                        with patch('os.remove') as os_remove_mock:
                            with patch('os.path.dirname', return_value="/fake/dir"):
                                with patch('os.listdir', return_value=[]):
                                    with patch('os.rmdir') as os_rmdir_mock:
                                        await attachment_cache.remove_attachment(sample_attachment_info["attachment_id"])

                                        assert os_remove_mock.call_count == 2
                                        os_remove_mock.assert_any_call("/fake/dir/test123.jpg")
                                        os_remove_mock.assert_any_call("/fake/dir/test123.json")
                                        os_rmdir_mock.assert_called_once_with("/fake/dir")

            assert sample_attachment_info["attachment_id"] not in attachment_cache.attachments

    class TestStorageLimitsFunctionality:
        """Tests for storage limits functionality"""

        @pytest.mark.asyncio
        async def test_enforce_age_limit(self, attachment_cache, sample_attachment_info):
            """Test removing old attachments based on age"""
            sample_attachment_info["created_at"] = datetime.now()
            await attachment_cache.add_attachment("conv123", sample_attachment_info)

            old_info = sample_attachment_info.copy()
            old_info["attachment_id"] = "old123"
            old_info["created_at"] = datetime.now() - timedelta(days=31)  # Older than max_age_days
            await attachment_cache.add_attachment("conv123", old_info)

            with patch.object(attachment_cache, 'remove_attachment') as remove_mock:
                await attachment_cache._enforce_age_limit()
                remove_mock.assert_called_once_with("old123")

        @pytest.mark.asyncio
        async def test_enforce_total_limit(self, attachment_cache):
            """Test enforcing the maximum number of attachments"""
            attachment_cache.max_total_attachments = 2

            for i in range(5):
                info = {
                    "attachment_id": f"test{i}",
                    "attachment_type": "photo",
                    "created_at": datetime.now() - timedelta(minutes=i),  # Progressively older
                    "file_extension": "jpg",
                    "size": 12345,
                    "processable": True,
                    "content": None
                }
                await attachment_cache.add_attachment(f"conv{i}", info)
            assert len(attachment_cache.attachments) == 5

            with patch.object(attachment_cache, 'remove_attachment') as remove_mock:
                await attachment_cache._enforce_total_limit()

                assert remove_mock.call_count == 3
                remove_mock.assert_any_call("test2")
                remove_mock.assert_any_call("test3")
                remove_mock.assert_any_call("test4")
