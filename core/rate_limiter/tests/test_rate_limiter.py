import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

from core.utils.config import Config
from core.rate_limiter.rate_limiter import RateLimiter

class TestRateLimiter:
    """Tests for the RateLimiter class"""

    @pytest.fixture
    def mock_config(self):
        """Create a mock config with rate limiting settings"""
        config = MagicMock(spec=Config)
        config.get_setting.side_effect = lambda section, key: {
            "global_rpm": 30,
            "per_conversation_rpm": 20,
            "message_rpm": 10
        }.get(key, None)
        return config

    @pytest.fixture
    def rate_limiter(self, mock_config):
        """Create a RateLimiter instance with mocked config"""
        RateLimiter._instance = None
        return RateLimiter(mock_config)

    class TestInitialization:
        """Tests for RateLimiter initialization"""

        def test_initialization(self, rate_limiter, mock_config):
            """Test that rate limiter initializes with correct settings"""
            assert rate_limiter.global_rpm == 30
            assert rate_limiter.per_conversation_rpm == 20
            assert rate_limiter.message_rpm == 10
            assert rate_limiter.config == mock_config
            assert rate_limiter.last_global_request == 0
            assert rate_limiter.global_request_count == 0
            assert isinstance(rate_limiter.last_conversation_requests, dict)
            assert isinstance(rate_limiter.per_conversation_request_counts, dict)

        def test_singleton_pattern(self, mock_config):
            """Test that get_instance returns the same instance"""
            first_instance = RateLimiter.get_instance(mock_config)
            second_instance = RateLimiter.get_instance(mock_config)

            assert first_instance is second_instance
            assert id(first_instance) == id(second_instance)

        def test_singleton_maintains_state(self, mock_config):
            """Test that the singleton maintains its state"""
            instance1 = RateLimiter.get_instance(mock_config)
            instance1.global_request_count = 42

            instance2 = RateLimiter.get_instance(mock_config)
            assert instance2.global_request_count == 42

    class TestWaitTimeCalculation:
        """Tests for wait time calculation"""

        @pytest.mark.asyncio
        async def test_get_wait_time_initial(self, rate_limiter):
            """Test that initial wait time is zero"""
            assert await rate_limiter.get_wait_time("general") == 0
            assert await rate_limiter.get_wait_time("message") == 0
            assert await rate_limiter.get_wait_time("general", "conversation123") == 0

        @pytest.mark.asyncio
        async def test_get_wait_time_after_request(self, rate_limiter):
            """Test wait time calculation after a request"""
            rate_limiter.last_global_request = time.time()
            wait_time = await rate_limiter.get_wait_time("general")

            # Wait time should be close to 60/global_rpm seconds
            expected_wait = 60 / rate_limiter.global_rpm
            assert wait_time > 0
            assert wait_time <= expected_wait
            assert abs(wait_time - expected_wait) < 0.1  # Small margin for test execution time

        @pytest.mark.asyncio
        async def test_get_wait_time_conversation_specific(self, rate_limiter):
            """Test wait time calculation for conversation-specific limits"""
            conversation_id = "test_conversation"
            rate_limiter.last_global_request = time.time() - 10  # 10 seconds ago (low global wait)
            rate_limiter.last_conversation_requests[conversation_id] = time.time()  # Just now (high conversation wait)
            wait_time = await rate_limiter.get_wait_time("general", conversation_id)

            # Conversation wait should be higher than global wait
            expected_wait = 60 / rate_limiter.per_conversation_rpm
            assert wait_time > 0
            assert wait_time <= expected_wait
            assert abs(wait_time - expected_wait) < 0.1

        @pytest.mark.asyncio
        async def test_get_wait_time_message_specific(self, rate_limiter):
            """Test wait time calculation for message-specific limits"""
            rate_limiter.last_global_request = time.time() - 10  # 10 seconds ago (low global wait)
            rate_limiter.last_message_request = time.time()  # Just now (high message wait)
            wait_time = await rate_limiter.get_wait_time("message")

            # Message wait should be higher than global wait
            expected_wait = 60 / rate_limiter.message_rpm
            assert wait_time > 0
            assert wait_time <= expected_wait
            assert abs(wait_time - expected_wait) < 0.1

        @pytest.mark.asyncio
        async def test_get_wait_time_returns_maximum(self, rate_limiter):
            """Test that get_wait_time returns the maximum wait time"""
            conversation_id = "test_conversation"
            rate_limiter.last_global_request = time.time() - 5  # 5 seconds ago
            rate_limiter.last_conversation_requests[conversation_id] = time.time() - 1  # 1 second ago
            rate_limiter.last_message_request = time.time()  # Just now (should be highest)
            wait_time = await rate_limiter.get_wait_time("message", conversation_id)

            expected_wait = 60 / rate_limiter.message_rpm
            assert abs(wait_time - expected_wait) < 0.1

        @pytest.mark.asyncio
        async def test_get_wait_time_handles_error(self, rate_limiter):
            """Test that get_wait_time handles errors gracefully"""
            rate_limiter.global_rpm = 0
            wait_time = await rate_limiter.get_wait_time("general")
            assert wait_time == 1.0

    class TestRateLimiting:
        """Tests for applying rate limiting"""

        @pytest.mark.asyncio
        async def test_limit_request_no_wait(self, rate_limiter):
            """Test limit_request when no waiting is needed"""
            with patch.object(rate_limiter, "get_wait_time", return_value=0):
                with patch("asyncio.sleep") as mock_sleep:
                    await rate_limiter.limit_request("general")

                    mock_sleep.assert_not_called()
                    assert rate_limiter.global_request_count == 1
                    assert rate_limiter.last_global_request > 0

        @pytest.mark.asyncio
        async def test_limit_request_with_wait(self, rate_limiter):
            """Test limit_request when waiting is needed"""
            with patch.object(rate_limiter, "get_wait_time", return_value=0.5):
                with patch("asyncio.sleep") as mock_sleep:
                    await rate_limiter.limit_request("general")

                    mock_sleep.assert_called_once_with(0.5)
                    assert rate_limiter.global_request_count == 1
                    assert rate_limiter.last_global_request > 0

        @pytest.mark.asyncio
        async def test_limit_request_updates_conversation_counters(self, rate_limiter):
            """Test that limit_request updates conversation-specific counters"""
            conversation_id = "test_conversation"

            with patch.object(rate_limiter, "get_wait_time", return_value=0):
                await rate_limiter.limit_request("general", conversation_id)

                assert conversation_id in rate_limiter.last_conversation_requests
                assert rate_limiter.per_conversation_request_counts[conversation_id] == 1

        @pytest.mark.asyncio
        async def test_limit_request_updates_message_timestamp(self, rate_limiter):
            """Test that limit_request updates message timestamp for message type"""
            with patch.object(rate_limiter, "get_wait_time", return_value=0):
                await rate_limiter.limit_request("message")

                assert rate_limiter.last_message_request > 0

        @pytest.mark.asyncio
        async def test_limit_request_increments_counters(self, rate_limiter):
            """Test that limit_request increments counters correctly"""
            conversation_id = "test_conversation"

            with patch.object(rate_limiter, "get_wait_time", return_value=0):
                await rate_limiter.limit_request("general")
                await rate_limiter.limit_request("message", conversation_id)
                await rate_limiter.limit_request("general", conversation_id)

                assert rate_limiter.global_request_count == 3
                assert rate_limiter.per_conversation_request_counts[conversation_id] == 2

    class TestIntegration:
        """Integration tests for RateLimiter"""

        @pytest.mark.asyncio
        async def test_actual_waiting(self, rate_limiter):
            """Test that limit_request actually causes waiting"""
            rate_limiter.global_rpm = 60  # 1 per second
            await rate_limiter.limit_request("general")

            start_time = time.time()
            await rate_limiter.limit_request("general")

            elapsed = time.time() - start_time
            assert elapsed >= 0.9  # Should wait about 1 second (60/60)
