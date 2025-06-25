import asyncio
import logging
import pytest
import time

from unittest.mock import AsyncMock, MagicMock, patch
from src.adapters.slack_adapter.event_processors.incoming_file_processor import IncomingFileProcessor

class TestIncomingFileProcessor:
    """Tests for the Slack IncomingFileProcessor class"""

    @pytest.fixture
    def mock_client(self):
        """Create a mock Slack client"""
        client = AsyncMock()
        client.files_info.return_value = {
            "file": {
                "id": "F123456",
                "url_private": "https://slack.com/files/test.pdf",
                "url_private_download": "https://slack.com/files/download/test.pdf"
            }
        }
        return client

    @pytest.fixture
    def mock_adapter(self):
        """Create a mock Slack adapter"""
        adapter = AsyncMock()
        adapter.process_incoming_event = AsyncMock(return_value=None)
        return adapter

    @pytest.fixture
    def rate_limiter_mock(self):
        """Create a mock rate limiter"""
        rate_limiter = AsyncMock()
        rate_limiter.limit_request = AsyncMock(return_value=None)
        rate_limiter.get_wait_time = AsyncMock(return_value=0)
        return rate_limiter

    @pytest.fixture
    def file_processor(self, slack_config, mock_client, mock_adapter, rate_limiter_mock):
        """Create a file processor with mocked dependencies"""
        processor = IncomingFileProcessor(slack_config, mock_client, mock_adapter)
        processor.rate_limiter = rate_limiter_mock
        return processor

    @pytest.fixture
    def standard_file_event(self):
        """Create a standard file event"""
        return {
            "type": "message",
            "subtype": "file_share",
            "files": [
                {
                    "id": "F123456",
                    "name": "test.pdf",
                    "size": 5000,
                    "mimetype": "application/pdf",
                    "url_private": "https://slack.com/files/test.pdf",
                    "url_private_download": "https://slack.com/files/download/test.pdf"
                }
            ],
            "ts": "1234567890.123456",
            "user": "U123456",
            "team": "T123456",
            "channel": "C123456"
        }

    @pytest.fixture
    def media_file_event(self):
        """Create a media file event"""
        return {
            "type": "message",
            "subtype": "slack_video",
            "files": [
                {
                    "id": "F789012",
                    "name": "test.mp4",
                    "size": 5000000,
                    "mimetype": "video/mp4",
                    "url_private": "https://slack.com/files/test.mp4",
                    "url_private_download": "https://slack.com/files/download/test.mp4",
                    "subtype": "slack_video",
                    "transcription": {"status": "processing"}
                }
            ],
            "ts": "1234567890.123456",
            "user": "U123456",
            "team": "T123456",
            "channel": "C123456"
        }

    @pytest.fixture
    def ready_media_file(self):
        """Create a ready media file info"""
        return {
            "id": "F789012",
            "name": "test.mp4",
            "size": 5000000,
            "mimetype": "video/mp4",
            "url_private": "https://slack.com/files/test.mp4",
            "url_private_download": "https://slack.com/files/download/test.mp4",
            "subtype": "slack_video",
            "transcription": {"status": "complete"},
            "mp4": "https://slack.com/files/mp4/test.mp4"
        }

    @pytest.mark.asyncio
    async def test_schedule_file_processing(self, file_processor, standard_file_event):
        """Test scheduling file processing tasks"""
        with patch.object(file_processor, "_process_file_with_retries", AsyncMock()):
            await file_processor.schedule_file_processing(standard_file_event)

            assert "F123456" in file_processor.processing_tasks

            for task, _ in file_processor.processing_tasks.values():
                task.cancel()

    @pytest.mark.asyncio
    async def test_get_file_status_cache_hit(self, file_processor):
        """Test file status caching"""
        file_processor.status_cache["F123456"] = {
            "info": {"id": "F123456"},
            "timestamp": time.time()
        }

        result = await file_processor._get_file_status("F123456")

        assert result["id"] == "F123456"
        assert not file_processor.client.files_info.called

    @pytest.mark.asyncio
    async def test_get_file_status_cache_miss(self, file_processor):
        """Test file status API call on cache miss"""
        result = await file_processor._get_file_status("F123456")

        file_processor.client.files_info.assert_called_once_with(file="F123456")
        assert "F123456" in file_processor.status_cache
        assert file_processor.status_cache["F123456"]["info"] == result

    @pytest.mark.asyncio
    async def test_is_file_ready_standard_file(self, file_processor):
        """Test checking if standard file is ready"""
        file_info = {
            "id": "F123456",
            "url_private_download": "https://slack.com/files/download/test.pdf"
        }

        assert file_processor._is_file_ready(file_info) == True

    @pytest.mark.asyncio
    async def test_is_file_ready_no_url(self, file_processor):
        """Test file not ready if no URLs"""
        assert file_processor._is_file_ready({"id": "F123456"}) == False

    @pytest.mark.asyncio
    async def test_is_file_ready_processing_video(self, file_processor):
        """Test video not ready if still processing"""
        file_info = {
            "id": "F789012",
            "url_private_download": "https://slack.com/files/download/test.mp4",
            "subtype": "slack_video",
            "transcription": {"status": "processing"}
        }

        assert file_processor._is_file_ready(file_info) == False

    @pytest.mark.asyncio
    async def test_is_file_ready_completed_video(self, file_processor, ready_media_file):
        """Test video ready when processing complete"""
        assert file_processor._is_file_ready(ready_media_file) == True

    @pytest.mark.asyncio
    async def test_is_file_ready_special_file(self, file_processor):
        """Test special file types are considered ready"""
        file_info = {
            "id": "F123456",
            "url_private_download": "https://slack.com/files/download/test.list",
            "mode": "list",
            "size": 0
        }

        assert file_processor._is_file_ready(file_info) == True

    @pytest.mark.asyncio
    async def test_process_file_with_retries_success_first_try(self,
                                                               file_processor,
                                                               standard_file_event):
        """Test successful file processing on first try"""
        with patch.object(file_processor, "_get_file_status", AsyncMock(
            return_value={"id": "F123456", "url_private_download": "https://example.com"}
        )):
            with patch.object(file_processor, "_process_file", AsyncMock()) as mock_process:
                await file_processor._process_file_with_retries(
                    "F123456",
                    {"id": "F123456"},
                    standard_file_event,
                    initial_delay=0.1,
                    max_retries=3,
                    backoff_factor=1.5
                )

                assert file_processor._get_file_status.call_count == 1
                mock_process.assert_called_once_with("F123456")

    @pytest.mark.asyncio
    async def test_process_file_with_retries_success_after_retry(self,
                                                                 file_processor,
                                                                 standard_file_event):
        """Test file processing succeeding after retry"""
        status_responses = [
            # First call - not ready
            {"id": "F123456", "url_private": None, "url_private_download": None},
            # Second call - ready
            {"id": "F123456", "url_private_download": "https://example.com"}
        ]

        async def get_status_side_effect(file_id):
            return status_responses.pop(0)

        with patch.object(file_processor, "_get_file_status", side_effect=get_status_side_effect):
            with patch.object(file_processor, "_process_file", AsyncMock()) as mock_process:
                with patch.object(logging, "warning") as mock_log:
                    await file_processor._process_file_with_retries(
                        "F123456",
                        {"id": "F123456"},
                        standard_file_event,
                        initial_delay=0.1,
                        max_retries=3,
                        backoff_factor=1.5
                    )

                    assert file_processor._get_file_status.call_count == 2
                    mock_process.assert_called_once_with("F123456")
                    assert not mock_log.called

    @pytest.mark.asyncio
    async def test_process_file_with_retries_max_retries(self,
                                                         file_processor,
                                                         standard_file_event):
        """Test file processing after max retries"""
        with patch.object(file_processor, "_get_file_status", AsyncMock(
            return_value={"id": "F123456", "url_private": None, "url_private_download": None}
        )):
            with patch.object(file_processor, "_process_file", AsyncMock()) as mock_process:
                with patch.object(logging, "warning") as mock_warning:
                    await file_processor._process_file_with_retries(
                        "F123456",
                        {"id": "F123456"},
                        standard_file_event,
                        initial_delay=0.1,
                        max_retries=3,
                        backoff_factor=1.5
                    )

                    assert file_processor._get_file_status.call_count == 3
                    mock_process.assert_called_once_with("F123456")

                    assert mock_warning.called
                    assert "not ready after 3 attempts" in mock_warning.call_args[0][0]
