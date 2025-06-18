import pytest

from src.core.cache.message_cache import CachedMessage
from src.core.conversation.base_reaction_handler import BaseReactionHandler

class TestBaseReactionHandler:

    @pytest.fixture
    def cached_message(self):
        """Create a cached message with initial reactions"""
        cached_msg = CachedMessage(
            message_id="123",
            conversation_id="456",
            text="Test message",
            sender_id="789",
            sender_name="Test User",
            timestamp=1234567890000,
            edit_timestamp=None,
            edited=False,
            is_from_bot=False,
            thread_id = None,
            reactions={"+1": 1}  # Initial reaction
        )
        return cached_msg

    class TestReactionManagement:
        """Tests for reaction addition and removal"""

        def test_add_reaction_new(self, cached_message):
            """Test adding a new reaction"""
            BaseReactionHandler.add_reaction(cached_message, "heart")

            assert "heart" in cached_message.reactions
            assert cached_message.reactions["heart"] == 1
            assert cached_message.reactions["+1"] == 1  # Original reaction still present

        def test_add_reaction_existing(self, cached_message):
            """Test increasing count of an existing reaction"""
            BaseReactionHandler.add_reaction(cached_message, "+1")

            assert cached_message.reactions["+1"] == 2

        def test_remove_reaction_existing(self, cached_message):
            """Test removing an existing reaction"""
            BaseReactionHandler.remove_reaction(cached_message, "+1")

            assert "+1" not in cached_message.reactions  # Should be removed when count reaches 0

        def test_remove_reaction_multiple(self, cached_message):
            """Test decreasing count of a reaction with multiple occurrences"""
            cached_message.reactions["heart"] = 2

            BaseReactionHandler.remove_reaction(cached_message, "heart")

            assert "heart" in cached_message.reactions
            assert cached_message.reactions["heart"] == 1  # Count decreased but still present

        def test_remove_reaction_nonexistent(self, cached_message):
            """Test removing a reaction that doesn't exist"""
            initial_reactions = cached_message.reactions.copy()

            BaseReactionHandler.remove_reaction(cached_message, "fire")

            assert cached_message.reactions == initial_reactions  # No change
